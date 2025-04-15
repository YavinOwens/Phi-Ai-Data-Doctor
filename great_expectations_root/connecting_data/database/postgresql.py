import great_expectations as ge
from ruamel import yaml
import ruamel
from great_expectations.core.batch import BatchRequest, RuntimeBatchRequest
from dotenv import load_dotenv, find_dotenv
import os 
import psycopg2
from sqlalchemy import create_engine
import pandas as pd 

load_dotenv(find_dotenv())

# Get your postgresql connection string from the environment variable
POSTGRES_CONNECTION_STRING = os.environ.get('DATABASE_CONNECTION_STRING')

def read_pg_tables(table_name):
    """
    Read postgresql table in pandas dataframe
    """
    engine = create_engine(POSTGRES_CONNECTION_STRING)
    df = pd.read_sql_query(f'select * from {table_name}',con=engine)
    return df

def get_pg_tables():
    """
    List all tables from a PostgreSQL database using a connection string
    """
    conn = psycopg2.connect(POSTGRES_CONNECTION_STRING)
    cursor = conn.cursor()

    query = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
    cursor.execute(query)

    tables = cursor.fetchall()
    tables = [t[0] for t in tables]
    cursor.close()
    conn.close()
    return tables

def postgresql_data_owners():
    """
    Map each postgresql with its data owner
    """
    tables = get_pg_tables()
    return {datasource : 'YMO@aidatadoctor.com' for datasource in tables}

class PostgreSQLDatasource():
    """
    Run Data Quality checks on PostgreSQL data database
    """
    def __init__(self, database, asset_name):
        """ 
        Init class attributes
        """
        self.database = database
        self.asset_name = asset_name
        self.datasource_name = f"{asset_name}_datasource"  # Use table name as datasource name
        self.expectation_suite_name = f"{asset_name}_expectation_suite"
        self.checkpoint_name = f"{asset_name}_checkpoint"
        self.context = ge.get_context()

    def add_or_update_datasource(self):
        """
        Create data source if it does not exist or updating existing one
        """
        datasource_yaml = rf"""
        name: {self.datasource_name}
        class_name: Datasource
        execution_engine:
            class_name: SqlAlchemyExecutionEngine
            connection_string: {POSTGRES_CONNECTION_STRING}
        data_connectors:
            default_runtime_data_connector_name:
                class_name: RuntimeDataConnector
                batch_identifiers:
                    - default_identifier_name
            default_inferred_data_connector_name:
                class_name: InferredAssetSqlDataConnector
                include_schema_name: true
        """
        self.context.test_yaml_config(datasource_yaml)
        self.context.add_datasource(**yaml.load(datasource_yaml, Loader=ruamel.yaml.Loader))

    def configure_datasource(self):
        """
        Add a RuntimeDataConnector
        """
        batch_request = RuntimeBatchRequest(
            datasource_name=self.datasource_name,  # Use the datasource_name, not database name
            data_connector_name="default_runtime_data_connector_name",
            data_asset_name=self.asset_name,  # this can be anything that identifies this data
            runtime_parameters={"query": f"SELECT * from public.{self.asset_name} LIMIT 10"},
            batch_identifiers={"default_identifier_name": "default_identifier"},
        )
        return batch_request

    def add_or_update_ge_suite(self):
        """
        create expectation suite if not exist and update it if there is already a suite
        """
        self.context.add_or_update_expectation_suite(
                     expectation_suite_name = self.expectation_suite_name)

    def get_validator(self):
        """
        Retrieve a validator object for a fine grain adjustment on the expectation suite.
        """
        self.add_or_update_datasource()
        batch_request = self.configure_datasource()
        self.add_or_update_ge_suite()
        validator = self.context.get_validator(batch_request=batch_request,
                                               expectation_suite_name=self.expectation_suite_name,
                                        )
        return validator, batch_request

    def run_expectation(self, expectation):
        """
        Run your dataquality checks here
        """
        validator, batch_request = self.get_validator()
        
        try:
            # Handle both string and dict expectations
            if isinstance(expectation, dict):
                # Handle the case where expectation is already a dictionary
                expectation_type = expectation.get('expectation_type')
                kwargs = expectation.get('kwargs', {})
                
                if not expectation_type:
                    raise ValueError("Invalid expectation format: missing 'expectation_type'")
                
                # Special handling for regex expectations on non-text columns
                if expectation_type == 'expect_column_values_to_match_regex':
                    # Get column type from database
                    conn = psycopg2.connect(POSTGRES_CONNECTION_STRING)
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        SELECT data_type 
                        FROM information_schema.columns 
                        WHERE table_name = '{self.asset_name}' 
                        AND column_name = '{kwargs.get("column")}'
                    """)
                    column_type = cursor.fetchone()
                    cursor.close()
                    conn.close()

                    # If column is not text/varchar, modify the query to cast it
                    if column_type and column_type[0] not in ['text', 'character varying', 'varchar']:
                        # Create a temporary view with the cast column
                        conn = psycopg2.connect(POSTGRES_CONNECTION_STRING)
                        cursor = conn.cursor()
                        try:
                            cursor.execute(f"""
                                CREATE OR REPLACE VIEW temp_{self.asset_name}_cast AS 
                                SELECT *, CAST({kwargs.get("column")} AS TEXT) as {kwargs.get("column")}_text 
                                FROM {self.asset_name}
                            """)
                            conn.commit()
                            # Update kwargs to use the cast column
                            kwargs["column"] = f"{kwargs.get('column')}_text"
                        except Exception as e:
                            print(f"Error creating temporary view: {str(e)}")
                        finally:
                            cursor.close()
                            conn.close()
                
                # Convert dict to function call
                expectation_code = f"{expectation_type}(**{kwargs})"
                print(f"Running expectation: {expectation_code}")
                
                # Execute the expectation
                local_vars = {"validator": validator}
                try:
                    exec(f"expectation_result = validator.{expectation_code}", globals(), local_vars)
                    expectation_result = local_vars.get("expectation_result")
                    if expectation_result is None:
                        raise ValueError(f"Failed to execute expectation: {expectation_code}")
                except AttributeError as e:
                    raise ValueError(f"Invalid expectation type: {expectation_type}. {str(e)}")
                except Exception as e:
                    raise ValueError(f"Error executing expectation: {str(e)}")
            else:
                # Handle string format (legacy)
                def my_function(expectation, validator):
                    local_vars = {"validator": validator}
                    exec(f"expectation_result = validator.{expectation}", globals(), local_vars)
                    return local_vars.get("expectation_result")
                
                expectation_result = my_function(expectation, validator)
            
            validator.save_expectation_suite(discard_failed_expectations=False)
            self.run_ge_checkpoint(batch_request)
            return expectation_result
        except Exception as e:
            print(f"Error running expectation: {str(e)}")
            raise
    
    def add_or_update_ge_checkpoint(self):
        """
        Create new GE checkpoint or update an existing one using the modern API.
        """
        try:
            # Try to delete existing checkpoint if it exists
            try:
                self.context.delete_checkpoint(name=self.checkpoint_name)
            except:
                pass  # Ignore if checkpoint doesn't exist

            # Define the checkpoint configuration using the modern Checkpoint structure
            checkpoint_config = f"""
name: {self.checkpoint_name}
config_version: 1.0
class_name: Checkpoint
run_name_template: '%Y%m%d-%H%M%S-{self.asset_name}-run'
validations:
  - batch_request:
      datasource_name: {self.datasource_name}
      data_connector_name: default_runtime_data_connector_name
      data_asset_name: {self.asset_name}
      runtime_parameters:
        query: SELECT * from public.{self.asset_name}
      batch_identifiers:
        default_identifier_name: default_identifier
    expectation_suite_name: {self.expectation_suite_name}
action_list:
  - name: store_validation_result
    action:
      class_name: StoreValidationResultAction
  - name: store_evaluation_params
    action:
      class_name: StoreEvaluationParametersAction
  - name: update_data_docs
    action:
      class_name: UpdateDataDocsAction
      site_names: []
"""
            # Add the new checkpoint
            self.context.add_checkpoint(**yaml.safe_load(checkpoint_config))
        except Exception as e:
            print(f"Error creating/updating checkpoint: {str(e)}")
            raise

    def run_ge_checkpoint(self, batch_request):
        """
        Run GE checkpoint
        """
        self.add_or_update_ge_checkpoint()

        self.context.run_checkpoint(
                checkpoint_name = self.checkpoint_name,
                validations=[
                            {
                            "batch_request": batch_request,
                            "expectation_suite_name": self.expectation_suite_name,
                            }
                            ],
                )



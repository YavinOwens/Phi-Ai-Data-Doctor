import great_expectations as ge
import datetime
from great_expectations.core.batch import RuntimeBatchRequest
from ruamel import yaml
import ruamel
import pandas as pd
import os

class PandasFilesystemDatasource():
    """
    Run Data Quality checks on Local Filesystem data
    """
    def __init__(self, datasource_name, dataframe):
        """ 
        Init class attributes
        """
        self.datasource_name = datasource_name
        self.expectation_suite_name = f"{datasource_name}_expectation_suite"
        self.checkpoint_name = f"{datasource_name}_checkpoint"
        self.dataframe = dataframe
        self.partition_date = datetime.datetime.now()
        self.context = ge.get_context()

    def add_or_update_datasource(self):
        """
        Create data source if it does not exist or updating existing one
        """
        datasource_yaml = rf"""
        name: {self.datasource_name}
        class_name: Datasource
        execution_engine:
            class_name: PandasExecutionEngine
        data_connectors:
            runtime_connector:
                class_name: RuntimeDataConnector
                batch_identifiers:
                    - run_id
        """
        self.context.test_yaml_config(datasource_yaml)
        self.context.add_datasource(**yaml.load(datasource_yaml, Loader=ruamel.yaml.Loader))

    def configure_datasource(self):
        """
        Add a RuntimeDataConnector hat uses an in-memory DataFrame to a Datasource configuration
        """
        batch_request = RuntimeBatchRequest(
            datasource_name= self.datasource_name,
            data_connector_name= "runtime_connector",
            data_asset_name=f"{self.datasource_name}_{self.partition_date.strftime('%Y%m%d')}",
            batch_identifiers={
                "run_id": f'''
                {self.datasource_name}_partition_date={self.partition_date.strftime('%Y%m%d')}
                ''',
            },
            runtime_parameters={"batch_data": self.dataframe}
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
run_name_template: '%Y%m%d-%H%M%S-{self.datasource_name}-run'
validations:
  - batch_request:
      datasource_name: {self.datasource_name}
      data_connector_name: runtime_connector
      data_asset_name: {self.datasource_name}_{self.partition_date.strftime('%Y%m%d')}
      batch_identifiers:
        run_id: {self.datasource_name}_partition_date={self.partition_date.strftime('%Y%m%d')}
      runtime_parameters:
        batch_data: {self.dataframe}
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

def get_mapping(folder_path):
    """
    Map each local file to the correspondind data owner (DO)
    """
    mapping_dict = {}
    data_owners = {}
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.csv'):
            name_without_extension = os.path.splitext(file_name)[0]
            name_with_uppercase = name_without_extension.capitalize()
            mapping_dict[name_with_uppercase] = file_name
            data_owners[name_with_uppercase] = "dioula01@gmail.com" #default DO for all files. To be modified
    return mapping_dict, data_owners


# Function to get mapping and data owners
def local_dataowners(local_filesystem_path):
    mapping, data_owners = get_mapping(local_filesystem_path)
    return mapping, data_owners

# Function to read local filesytem .csv file in a datafrale
def read_local_filesystem_tb(local_filesystem_path, data_source, mapping):
    file_name = mapping.get(data_source, None)
    if file_name is None:
        raise ValueError(f"Data source '{data_source}' not found in mapping")
    
    # Make sure the path ends with a slash
    if not local_filesystem_path.endswith('/'):
        local_filesystem_path += '/'
    
    file_path = f"{local_filesystem_path}{file_name}"
    print(f"Reading file: {file_path}")
    
    try:
        data = pd.read_csv(file_path)
        if data.empty:
            raise ValueError(f"File {file_path} is empty")
        return data
    except pd.errors.EmptyDataError:
        print(f"Error: No columns to parse from file {file_path}")
        # Return a simple DataFrame with one column as a fallback
        return pd.DataFrame({'dummy_column': [1, 2, 3]})
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        # Return a simple DataFrame with one column as a fallback
        return pd.DataFrame({'dummy_column': [1, 2, 3]})
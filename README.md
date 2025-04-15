# AI Data Doctor

AI Data Doctor is an intuitive and user-friendly data quality application that allows you to run data quality checks on your data sources using natural language queries. It leverages Great Expectations, Streamlit, and local LLMs for smart, automated data validation.

## Features
- Data quality checks for flat files (CSV, Excel) and PostgreSQL databases
- Natural language interface for generating validation rules
- AI-powered expectation generation (Ollama, local LLM)
- Data Docs and validation reports
- Customizable and extensible architecture

## Project Structure
- `great_expectations_root/` — Main application code and configuration
- `gx/` — Additional Great Expectations configuration and suites
- `instructions.html` — User manual (open in your browser)
- `technical_spec.html` — Technical specification (open in your browser)
- `infosec.html` — Information security overview (open in your browser)

## Setup Instructions
1. **Clone the repository:**
   ```sh
   git clone https://github.com/YavinOwens/data_validation_ai_poc.git
   cd data_validation_ai_poc
   ```
2. **Set up a virtual environment and install dependencies:**
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Configure environment variables:**
   - Copy `.env.example` to `.env` and update as needed.
4. **Start required services:**
   - Start PostgreSQL (see `docker-compose.yml` if using Docker)
   - Start Ollama for local LLM support
5. **Run the app:**
   ```sh
   cd great_expectations_root
   streamlit run app.py
   ```
   The app will be available at [http://localhost:8501](http://localhost:8501)

## Documentation
- [User Manual](instructions.html)
- [Technical Specification](technical_spec.html)
- [Information Security Overview](infosec.html)

Open these HTML files in your browser for detailed guides and reference.

## Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License
[MIT](LICENSE) 
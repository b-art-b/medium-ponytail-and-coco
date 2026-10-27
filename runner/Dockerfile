FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==9.1.1 streamlit==1.66.0 dbt-snowflake==1.12.3
ENV PYTHONDONTWRITEBYTECODE=1 DBT_SEND_ANONYMOUS_USAGE_STATS=false
WORKDIR /candidate

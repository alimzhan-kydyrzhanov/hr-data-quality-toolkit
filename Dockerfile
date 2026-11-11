FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m pytest -q
CMD ["python", "-m", "hr_dq.main", "--out", "output/hr_data_quality_report.xlsx"]

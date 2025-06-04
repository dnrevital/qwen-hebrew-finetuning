import pandas as pd
import os
from pathlib import Path

# Configuration
SAMPLE_SIZE = 10000  # Number of rows to sample from each file
INPUT_DIR = "clustered_datasets"
OUTPUT_DIR = "clustered_datasets_csv"

def process_file(excel_file):
    print(f"Processing {excel_file}...")
    
    # Read the Excel file
    df = pd.read_excel(excel_file)
    
    # Sample rows if the file is larger than our sample size
    if len(df) > SAMPLE_SIZE:
        df = df.sample(n=SAMPLE_SIZE, random_state=42)
    
    # Create output filename
    csv_filename = Path(excel_file).stem + '.csv'
    output_path = os.path.join(OUTPUT_DIR, csv_filename)
    
    # Save as CSV
    df.to_csv(output_path, index=False)
    print(f"Saved {csv_filename} with {len(df)} rows")

def main():
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Process all Excel files in the input directory
    excel_files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.xlsx')]
    
    for excel_file in excel_files:
        input_path = os.path.join(INPUT_DIR, excel_file)
        try:
            process_file(input_path)
        except Exception as e:
            print(f"Error processing {excel_file}: {str(e)}")

if __name__ == "__main__":
    main() 
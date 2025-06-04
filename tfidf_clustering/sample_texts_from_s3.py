import boto3
import pandas as pd
import os
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import random

# === CONFIGURATION ===
# Add your source datasets here. Each source will be sampled equally to reach TARGET_TEXTS
SOURCES = [
    "hebrew_tweets_text_clean_full-Deduped",
    "YifatDataBatch2-Round4-DedupedD2",
    "YifatDataBatch2-Round3-Deduped",
    "YifatDataBatch3-Round5-DedupedD2"
]

TARGET_TEXTS = 2_000_000  # Total number of texts to sample
S3_BUCKET = "israllm-datasets"
S3_PREFIX = "csv-dataset/"
OUTPUT_FILENAME = "social.csv"  # Name of the output file
OUTPUT_DIR = Path("data/cluster_samples")  # Output directory (relative to current directory)

def main():
    print("\n=== Starting Text Sampling from S3 ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nTarget number of texts: {TARGET_TEXTS:,}")
    print(f"Number of sources: {len(SOURCES)}")
    print(f"Output file: {OUTPUT_DIR / OUTPUT_FILENAME}")
    
    # Calculate texts per source
    texts_per_source = TARGET_TEXTS // len(SOURCES)
    print(f"Texts to sample per source: {texts_per_source:,}")
    
    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # Added parents=True to create data directory if needed
    print(f"\nUsing output directory: {OUTPUT_DIR.absolute()}")  # Show absolute path for clarity
    
    # Initialize S3 client
    s3 = boto3.client('s3')
    
    # Process each source
    all_sampled_texts = []  # Store all sampled texts
    
    for source in SOURCES:
        print(f"\nProcessing source: {source}")
        
        # List all files for this source
        paginator = s3.get_paginator('list_objects_v2')
        files = []
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
            for obj in page.get('Contents', []):
                if source in obj['Key']:
                    files.append(obj['Key'])
        
        print(f"Found {len(files)} files for source {source}")
        
        # Sample texts from files
        texts_processed = 0
        sampled_texts = []
        
        for file_key in tqdm(files, desc=f"Processing {source}"):
            if texts_processed >= texts_per_source:
                break
                
            try:
                # Download file temporarily
                local_file = f"temp_{os.path.basename(file_key)}"
                s3.download_file(S3_BUCKET, file_key, local_file)
                
                # Read file in chunks
                for chunk in pd.read_csv(local_file, chunksize=10000):
                    text_column = chunk.columns[1]  # Assuming second column is text
                    texts = chunk[text_column].astype(str).replace('nan', '').tolist()
                    
                    # Filter out empty texts
                    texts = [t for t in texts if t.strip()]
                    
                    # Add texts to our sample
                    remaining = texts_per_source - texts_processed
                    if remaining <= 0:
                        break
                        
                    if len(texts) <= remaining:
                        sampled_texts.extend(texts)
                        texts_processed += len(texts)
                    else:
                        # Randomly sample if we have too many texts
                        sampled = random.sample(texts, remaining)
                        sampled_texts.extend(sampled)
                        texts_processed += remaining
                
                # Clean up temporary file
                if os.path.exists(local_file):
                    os.remove(local_file)
                    
            except Exception as e:
                print(f"Warning: Could not process {file_key}: {str(e)}")
        
        print(f"Sampled {texts_processed:,} texts from {source}")
        all_sampled_texts.extend(sampled_texts)
    
    # Save combined results
    print("\nSaving results...")
    output_file = OUTPUT_DIR / OUTPUT_FILENAME
    df = pd.DataFrame({'text': all_sampled_texts})
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"Saved {len(df)} texts to {output_file}")
    
    print("\nSampling complete!")
    print(f"Results saved in: {OUTPUT_DIR.absolute()}")  # Show absolute path for clarity

if __name__ == "__main__":
    main() 
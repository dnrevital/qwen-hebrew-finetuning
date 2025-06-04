import pandas as pd
import json
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm
import numpy as np

# === CONFIGURATION ===
CLUSTERS_DIR = Path("data/utilimax_clusters")
OUTPUT_FILE = CLUSTERS_DIR / "word_count_statistics.json"

def count_words(text):
    """Count words in a text"""
    if not isinstance(text, str):
        return 0
    return len(text.split())

def analyze_cluster_file(file_path):
    """Analyze word counts in a cluster file"""
    print(f"\nAnalyzing {file_path.name}...")
    
    # Read the CSV file
    df = pd.read_csv(file_path, encoding='utf-8-sig')
    
    # Calculate word counts for each text
    df['word_count'] = df['text'].apply(count_words)
    
    # Calculate statistics
    total_texts = int(len(df))
    total_words = int(df['word_count'].sum())
    avg_words = float(df['word_count'].mean())
    min_words = int(df['word_count'].min())
    max_words = int(df['word_count'].max())
    
    # Convert distribution values to native Python types
    distribution = df['word_count'].value_counts().sort_index().to_dict()
    distribution = {int(k): int(v) for k, v in distribution.items()}
    
    return {
        'total_texts': total_texts,
        'total_words': total_words,
        'avg_words_per_text': avg_words,
        'min_words': min_words,
        'max_words': max_words,
        'word_count_distribution': distribution
    }

def main():
    print("\n=== Starting Word Count Analysis ===")
    
    # Get all cluster files
    cluster_files = list(CLUSTERS_DIR.glob("*.csv"))
    if not cluster_files:
        print(f"No cluster files found in {CLUSTERS_DIR}")
        return
    
    print(f"Found {len(cluster_files)} cluster files")
    
    # Analyze each cluster
    cluster_stats = {}
    total_words = 0
    total_texts = 0
    
    for cluster_num, file_path in enumerate(tqdm(cluster_files, desc="Analyzing clusters")):
        # Analyze the cluster
        stats = analyze_cluster_file(file_path)
        cluster_stats[str(cluster_num)] = stats  # Convert cluster number to string for JSON
        
        # Update totals
        total_words += stats['total_words']
        total_texts += stats['total_texts']
    
    # Prepare final statistics
    final_stats = {
        'overall': {
            'total_clusters': len(cluster_files),
            'total_texts': total_texts,
            'total_words': total_words,
            'avg_words_per_text': float(total_words / total_texts) if total_texts > 0 else 0.0
        },
        'clusters': cluster_stats
    }
    
    # Save results
    print(f"\nSaving statistics to {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_stats, f, ensure_ascii=False, indent=2)
    
    # Print summary
    print("\nAnalysis Summary:")
    print(f"Total clusters: {final_stats['overall']['total_clusters']}")
    print(f"Total texts: {final_stats['overall']['total_texts']:,}")
    print(f"Total words: {final_stats['overall']['total_words']:,}")
    print(f"Average words per text: {final_stats['overall']['avg_words_per_text']:.2f}")
    
    print("\nPer cluster statistics:")
    for cluster_num, stats in cluster_stats.items():
        print(f"\nCluster {cluster_num}:")
        print(f"  Texts: {stats['total_texts']:,}")
        print(f"  Words: {stats['total_words']:,}")
        print(f"  Avg words per text: {stats['avg_words_per_text']:.2f}")
        print(f"  Min words: {stats['min_words']}")
        print(f"  Max words: {stats['max_words']}")

if __name__ == "__main__":
    main() 
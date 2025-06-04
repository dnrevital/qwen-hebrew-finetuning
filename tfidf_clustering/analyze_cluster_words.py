import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans
import os
import re
import json
import boto3
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from text_processing_config import *
from tqdm import tqdm
from sklearn.exceptions import NotFittedError
import time

# Configuration
INPUT_DIR = "clustered_datasets_csv"
TOP_N_WORDS = 20  # Number of top distinctive words to show per cluster
MIN_WORD_LENGTH = 4  # Increased minimum word length to filter out codes
MAX_WORD_LENGTH = 20  # Maximum word length to filter out very long strings

# === CONFIGURATION ===
SELECTED_DATASET_NAME = "AllOfNewHebrewWikipediaWithArticles-Oct29-2023"  # אפשר לשנות ל-AllOfNewHebrewWikipediaWithArticles-Oct29-2023
N_CLUSTERS = 3
TARGET_TEXTS = 2_000_000

class HebrewTextAnalyzer:
    def __init__(self, input_dir="clustered_datasets_csv", n_clusters=7, batch_size=5000, 
                 change_threshold=0.3, checkpoint_frequency=10000,
                 tfidf_weights={'low': 0.1, 'medium': 1.0, 'high': 0.5},
                 filter_patterns=None, target_texts=None, processed_sources=None, dataset_names=None,
                 start_fresh=False, output_dir=None):
        self.input_dir = input_dir
        self.n_clusters = n_clusters
        self.batch_size = batch_size
        self.change_threshold = change_threshold
        self.checkpoint_frequency = checkpoint_frequency
        self.tfidf_weights = tfidf_weights
        self.filter_patterns = filter_patterns or []
        self.target_texts = target_texts
        self.processed_sources = processed_sources or set()
        self.dataset_names = dataset_names or []
        self.start_fresh = start_fresh
        self.output_dir = output_dir
        
        # Add last save time tracking
        self.last_save_time = 0
        self.min_save_interval = 300  # Minimum 5 minutes between saves
        
        # Initialize clustering model
        self.kmeans = MiniBatchKMeans(
            n_clusters=n_clusters,
            batch_size=batch_size,
            max_iter=100,
            compute_labels=True,
            random_state=42
        )
        
        # Initialize storage
        self.texts_data = []
        self.text_sources = []
        self.current_labels = []
        self.previous_labels = None
        self.processed_count = 0
        self.cluster_centers_history = []
        self.cluster_stats = defaultdict(lambda: defaultdict(list))
        self.is_fitted = False
        
        # Initialize vectorizer with custom weights
        self.vectorizer = TfidfVectorizer(
            **TFIDF_CONFIG,
            token_pattern=r'(?u)\b[\u0590-\u05FF\uFB1D-\uFB4F]{4,20}\b',
        )
        
        # Create output directory with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = output_dir or Path(f"cluster_analysis_output_{SELECTED_DATASET_NAME}_{N_CLUSTERS}clusters_{timestamp}")
        self.output_dir.mkdir(exist_ok=True)
        
        # Save configuration
        self._save_config()
        
        # Load previous state if exists
        self._load_state()

    def _save_config(self):
        """Save current configuration"""
        config = {
            'n_clusters': self.n_clusters,
            'batch_size': self.batch_size,
            'change_threshold': self.change_threshold,
            'checkpoint_frequency': self.checkpoint_frequency,
            'tfidf_weights': self.tfidf_weights,
            'filter_patterns': self.filter_patterns,
            'target_texts': self.target_texts,
            'processed_sources': list(self.processed_sources),
            'dataset_names': self.dataset_names,
            'timestamp': datetime.now().isoformat()
        }
        
        config_file = self.output_dir / "config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def _load_state(self):
        """Load previous analysis state if it exists"""
        state_file = self.output_dir / "analyzer_state.json"
        if state_file.exists() and not self.start_fresh:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                self.processed_count = state.get('processed_count', 0)
                print(f"Loaded previous state. Processed count: {self.processed_count}")
        else:
            if self.start_fresh:
                print("Starting fresh analysis (ignoring previous state)")
            else:
                print("No previous state found, starting fresh")
            self.processed_count = 0
            
        # Initialize clustering model
        self.kmeans = MiniBatchKMeans(
            n_clusters=self.n_clusters,
            batch_size=self.batch_size,
            max_iter=100,
            compute_labels=True,
            random_state=42
        )
        
        # Initialize storage
        self.texts_data = []
        self.text_sources = []
        self.current_labels = []
        self.previous_labels = None
        self.cluster_centers_history = []
        self.cluster_stats = defaultdict(lambda: defaultdict(list))
        self.is_fitted = False
        
        # Initialize vectorizer with custom weights
        self.vectorizer = TfidfVectorizer(
            **TFIDF_CONFIG,
            token_pattern=r'(?u)\b[\u0590-\u05FF\uFB1D-\uFB4F]{4,20}\b',
        )

    def _save_state(self):
        """Save current analysis state"""
        if not self.is_fitted:
            print("Model not fitted yet, skipping state save")
            return
            
        print(f"\nSaving state to {self.output_dir}")
        state = {
            'processed_count': self.processed_count,
            'timestamp': datetime.now().isoformat(),
            'cluster_centers': self.kmeans.cluster_centers_.tolist(),
            'n_clusters': self.n_clusters,
            'total_texts': len(self.texts_data),
            'progress': {
                'processed_texts': self.processed_count,
                'target_texts': self.target_texts,
                'processed_sources': len(self.processed_sources),
                'total_sources': len(self.dataset_names)
            }
        }
        
        state_file = self.output_dir / "analyzer_state.json"
        print(f"Writing to {state_file}")
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print("State saved successfully")

    def clean_text(self, text, show_debug=False):
        """Clean and filter text"""
        if not isinstance(text, str):
            if show_debug:
                print(f"Warning: Non-string input: {type(text)}")
            return "", {"non_string": 1}
        
        original_text = text
        
        # Convert abbreviations to full form
        for abbr, full in ABBREVIATIONS_MAPPING.items():
            text = text.replace(abbr, full)
        
        # Remove special characters and digits
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\d+', '', text)
        
        # Remove codes
        for code in CODES_TO_REMOVE:
            text = text.replace(code, ' ')
        
        # Apply custom filter patterns
        for pattern in self.filter_patterns:
            text = re.sub(pattern, ' ', text)
        
        # Split into words and filter
        words = text.split()
        filtered_words = []
        rejected_words = defaultdict(int)
        
        for word in words:
            word = word.strip()
            # Track why words are rejected
            if len(word) < MIN_WORD_LENGTH:
                rejected_words['too_short'] += 1
            elif len(word) > MAX_WORD_LENGTH:
                rejected_words['too_long'] += 1
            elif not self.is_mostly_hebrew(word, show_debug):
                rejected_words['not_hebrew'] += 1
            elif self.is_date_related(word):
                rejected_words['date_related'] += 1
            else:
                filtered_words.append(word)
        
        cleaned = ' '.join(filtered_words)
        
        # If showing debug info
        if show_debug:
            print(f"\nText Filtering Debug:")
            print(f"Original text length: {len(original_text)}")
            print(f"Words before filtering: {len(words)}")
            print("Rejection reasons:")
            for reason, count in rejected_words.items():
                print(f"  - {reason}: {count} words")
            print(f"Original text sample: {original_text[:200]}")
            print(f"First few original words: {words[:5] if words else 'No words'}")
            if cleaned:
                print(f"Cleaned text sample: {cleaned[:200]}")
            else:
                print("No words passed filtering")
            print("-" * 50)
        
        return cleaned, rejected_words

    def is_mostly_hebrew(self, text, show_debug=False):
        """Check if text contains mostly Hebrew characters"""
        if not text:
            return False
            
        hebrew_chars = sum(1 for c in text if '\u0590' <= c <= '\u05FF' or '\uFB1D' <= c <= '\uFB4F')
        total_chars = len(text)
        
        # Print debug info for rejected text
        ratio = hebrew_chars / total_chars if total_chars > 0 else 0
        if show_debug and ratio < 0.3:  # If text is rejected due to low Hebrew ratio
            print(f"Hebrew Check for word '{text}':")
            print(f"Total chars: {total_chars}")
            print(f"Hebrew chars: {hebrew_chars}")
            print(f"Ratio: {ratio:.2f}")
        
        return ratio >= 0.3  # Reduced threshold to 30% Hebrew characters

    def is_date_related(self, text):
        """Check if text is date-related"""
        # Add your date-related patterns here
        date_patterns = ['תאריך', 'יום', 'חודש', 'שנה']
        return any(pattern in text for pattern in date_patterns)

    def process_batch(self, texts, source_names):
        """Process a batch of texts and update clusters"""
        if not texts:  # Skip empty batches
            return []
            
        # Clean and vectorize new texts
        cleaned_texts = []
        total_rejected = defaultdict(int)
        
        # Process texts with progress bar
        for text in tqdm(texts, desc="Cleaning texts", unit="text", leave=False):
            cleaned, rejection_stats = self.clean_text(text)
            if cleaned:
                cleaned_texts.append(cleaned)
            for reason, count in rejection_stats.items():
                total_rejected[reason] += count
        
        if not cleaned_texts:  # Skip if no valid texts after cleaning
            return []
        
        # Update vocabulary and transform texts
        try:
            # Check if vectorizer is fitted by trying to transform
            try:
                self.vectorizer.transform([cleaned_texts[0]])
                is_fitted = True
            except NotFittedError:
                is_fitted = False
            
            if not is_fitted:
                vectorized_texts = self.vectorizer.fit_transform(cleaned_texts)
            else:
                vectorized_texts = self.vectorizer.transform(cleaned_texts)
            
            # Update model with new texts
            if not self.is_fitted:
                self.kmeans.fit(vectorized_texts)
                self.is_fitted = True
            else:
                self.kmeans.partial_fit(vectorized_texts)
            
            # Store texts and their sources
            self.texts_data.extend(cleaned_texts)
            self.text_sources.extend(source_names[:len(cleaned_texts)])
            
            # Get new labels for all texts
            all_vectorized = self.vectorizer.transform(self.texts_data)
            self.current_labels = self.kmeans.predict(all_vectorized)
            
            # Track changes and update statistics
            changes = self._analyze_cluster_changes()
            self._update_cluster_stats(changes)
            
            # Save state periodically with minimum time interval
            self.processed_count += len(cleaned_texts)
            current_time = time.time()
            
            # Check if we should save
            should_save = False
            if self.processed_count % self.checkpoint_frequency == 0:
                print(f"\nReached checkpoint: {self.processed_count} texts processed")
                should_save = True
            
            if current_time - self.last_save_time >= self.min_save_interval:
                print(f"\nTime interval reached: {int(current_time - self.last_save_time)} seconds since last save")
                should_save = True
            
            if should_save:
                print(f"Saving state and results...")
                self._save_state()
                self._save_interim_results()
                self.last_save_time = current_time
                print(f"Save completed at {time.strftime('%H:%M:%S')}")
            
            return changes
            
        except Exception as e:
            print(f"\nError in process_batch: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def _analyze_cluster_changes(self):
        """Track changes in cluster assignments"""
        changes = []
        if self.previous_labels is not None:
            for idx, (old_label, new_label) in enumerate(zip(self.previous_labels, self.current_labels)):
                if old_label != new_label:
                    similarity = self._calculate_cluster_similarity(old_label, new_label)
                    if similarity < self.change_threshold:
                        changes.append({
                            'text_id': idx,
                            'text': self.texts_data[idx],
                            'source': self.text_sources[idx],
                            'old_cluster': int(old_label),
                            'new_cluster': int(new_label),
                            'similarity': float(similarity)
                        })
        
        self.previous_labels = self.current_labels.copy()
        return changes

    def _calculate_cluster_similarity(self, cluster1, cluster2):
        """Calculate similarity between two cluster centers"""
        if not self.is_fitted:
            return 0.0
            
        center1 = self.kmeans.cluster_centers_[cluster1]
        center2 = self.kmeans.cluster_centers_[cluster2]
        return float(np.dot(center1, center2) / 
                    (np.linalg.norm(center1) * np.linalg.norm(center2)))

    def _update_cluster_stats(self, changes):
        """Update statistics for each cluster"""
        # Track cluster stability
        for change in changes:
            self.cluster_stats[change['old_cluster']]['texts_moved_out'].append(change['text'])
            self.cluster_stats[change['new_cluster']]['texts_moved_in'].append(change['text'])
        
        # Update current cluster contents with source information
        for idx, label in enumerate(self.current_labels):
            self.cluster_stats[int(label)]['current_texts'].append({
                'text': self.texts_data[idx],
                'source': self.text_sources[idx]
            })

    def _save_interim_results(self):
        """Save interim analysis results"""
        if not self.is_fitted:
            print("Model not fitted yet, skipping interim results save")
            return
            
        print(f"Saving interim results to {self.output_dir}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create a readable weight string
        weights = self.tfidf_weights
        weight_str = f"w{weights['low']}_{weights['medium']}_{weights['high']}"
        
        results_file = self.output_dir / f"cluster_results_{weight_str}_{timestamp}.json"
        
        # Get top words for each cluster
        feature_names = self.vectorizer.get_feature_names_out()
        cluster_words = {}
        source_distribution = {}  # Track source distribution per cluster
        
        for i in range(self.n_clusters):
            center = self.kmeans.cluster_centers_[i]
            top_indices = np.argsort(center)[-20:][::-1]
            top_words = [(feature_names[j], float(center[j])) 
                        for j in top_indices]
            cluster_words[i] = top_words
            
            # Calculate source distribution for this cluster
            cluster_texts = self.cluster_stats[i]['current_texts']
            source_counts = defaultdict(int)
            for text_info in cluster_texts:
                source = text_info['source']
                source_counts[source] += 1
            
            source_distribution[i] = dict(source_counts)
        
        # Prepare results
        results = {
            'timestamp': timestamp,
            'processed_count': self.processed_count,
            'clusters': {
                str(i): {
                    'top_words': cluster_words[i],
                    'size': int(np.sum(self.current_labels == i)),
                    'source_distribution': source_distribution[i],
                    'stability': {
                        'texts_moved_out': len(self.cluster_stats[i]['texts_moved_out']),
                        'texts_moved_in': len(self.cluster_stats[i]['texts_moved_in'])
                    }
                }
                for i in range(self.n_clusters)
            }
        }
        
        print(f"Writing results to {results_file}")
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("Interim results saved successfully")

    def process_text_stats(self, text):
        """Calculate text statistics"""
        words = text.split()
        chars = sum(len(word) for word in words)
        size_bytes = len(text.encode('utf-8'))
        return {
            'word_count': len(words),
            'char_count': chars,
            'size_bytes': size_bytes
        }

    def save_cluster_datasets(self, output_dir):
        """Save datasets for each cluster"""
        print("\nSaving cluster datasets...")
        for cluster_id in range(self.n_clusters):
            cluster_texts = self.cluster_stats[cluster_id]['current_texts']
            if not cluster_texts:
                continue
                
            # Create DataFrame for cluster
            data = []
            for text_info in cluster_texts:
                stats = self.process_text_stats(text_info['text'])
                data.append({
                    'text': text_info['text'],
                    'source': text_info['source'],
                    **stats
                })
            
            df = pd.DataFrame(data)
            output_file = output_dir / f"cluster_{cluster_id}_dataset.csv"
            # Save with UTF-8 encoding and BOM for better Hebrew support
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"Saved {len(df)} texts to {output_file}")

    def save_statistics(self, output_dir):
        """Save overall statistics"""
        print("\nSaving statistics...")
        stats = {
            'total_texts': self.processed_count,
            'clusters': {}  # Initialize clusters dictionary
        }
        
        for cluster_id in range(self.n_clusters):
            cluster_texts = self.cluster_stats[cluster_id]['current_texts']
            if not cluster_texts:
                continue
                
            # Calculate cluster statistics
            word_count = 0
            char_count = 0
            size_bytes = 0
            source_dist = defaultdict(int)
            
            for text_info in cluster_texts:
                text_stats = self.process_text_stats(text_info['text'])
                word_count += text_stats['word_count']
                char_count += text_stats['char_count']
                size_bytes += text_stats['size_bytes']
                source_dist[text_info['source']] += 1
            
            stats['clusters'][str(cluster_id)] = {  # Convert cluster_id to string for JSON
                'text_count': len(cluster_texts),
                'word_count': word_count,
                'char_count': char_count,
                'size_bytes': size_bytes,
                'source_distribution': dict(source_dist)
            }
        
        # Save statistics
        stats_file = output_dir / "statistics.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"Statistics saved to {stats_file}")

def main():
    print("\n=== Starting Cluster Analysis ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # S3 configuration
    s3_bucket = "mafat-datasets"
    s3_prefix = "csv-dataset/"
    dataset_name = SELECTED_DATASET_NAME

    # Create new output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"cluster_analysis_output_{dataset_name}_{N_CLUSTERS}clusters_{timestamp}")
    output_dir.mkdir(exist_ok=True)
    print(f"\nCreated new output directory: {output_dir}")
    print(f"Target number of texts: {TARGET_TEXTS:,}")

    # Initialize S3 client
    s3 = boto3.client('s3')

    # List all files in the S3 bucket with the given prefix and dataset name
    paginator = s3.get_paginator('list_objects_v2')
    files = []
    print(f"Listing files for dataset: {dataset_name}")
    for page in paginator.paginate(Bucket=s3_bucket, Prefix=s3_prefix):
        for obj in page.get('Contents', []):
            if dataset_name in obj['Key']:
                files.append(obj['Key'])

    # Select up to TARGET_TEXTS texts from the files
    selected_files = []
    texts_so_far = 0
    for file_key in files:
        if texts_so_far >= TARGET_TEXTS:
            break
        try:
            local_file = f"temp_{os.path.basename(file_key)}"
            s3.download_file(s3_bucket, file_key, local_file)
            with open(local_file, 'r', encoding='utf-8') as f:
                num_texts = sum(1 for _ in f) - 1
            if texts_so_far + num_texts > TARGET_TEXTS:
                texts_to_add = TARGET_TEXTS - texts_so_far
                print(f"  Partially adding {texts_to_add:,}/{num_texts:,} texts from {os.path.basename(file_key)}")
                selected_files.append((file_key, dataset_name, texts_to_add))
                texts_so_far += texts_to_add
            else:
                print(f"  Added {num_texts:,} texts from {os.path.basename(file_key)}")
                selected_files.append((file_key, dataset_name, None))
                texts_so_far += num_texts
            if os.path.exists(local_file):
                os.remove(local_file)
        except Exception as e:
            print(f"Warning: Could not process {file_key}: {str(e)}")

    print(f"\nSelected {len(selected_files)} files from dataset {dataset_name}")
    print(f"Estimated total texts: {texts_so_far:,} (target: {TARGET_TEXTS:,})")

    # Initialize analyzer
    analyzer = HebrewTextAnalyzer(
        n_clusters=N_CLUSTERS,
        batch_size=5000,
        change_threshold=0.3,
        checkpoint_frequency=10000,
        tfidf_weights={'low': 0.1, 'medium': 1.0, 'high': 0.5},
        filter_patterns=[
            r'\b(ינואר|פברואר|מרץ|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\b',
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b'
        ],
        output_dir=output_dir
    )

    print("\nProcessing files...")
    for file_key, source_name, max_texts in tqdm(selected_files, desc="Processing files"):
        basename = os.path.basename(file_key)
        try:
            local_file = f"temp_{basename}"
            s3.download_file(s3_bucket, file_key, local_file)
            if max_texts is not None:
                texts_processed = 0
                for chunk in pd.read_csv(local_file, chunksize=analyzer.batch_size):
                    text_column = chunk.columns[1]
                    texts = chunk[text_column].astype(str).replace('nan', '').tolist()
                    if texts_processed + len(texts) > max_texts:
                        texts = texts[:max_texts - texts_processed]
                    sources = [source_name] * len(texts)
                    analyzer.process_batch(texts, sources)
                    texts_processed += len(texts)
                    if texts_processed >= max_texts:
                        break
            else:
                for chunk in pd.read_csv(local_file, chunksize=analyzer.batch_size):
                    text_column = chunk.columns[1]
                    texts = chunk[text_column].astype(str).replace('nan', '').tolist()
                    sources = [source_name] * len(texts)
                    analyzer.process_batch(texts, sources)
            if os.path.exists(local_file):
                os.remove(local_file)
        except Exception as e:
            print(f"Warning: Could not process file {file_key}: {str(e)}")

    # Save final results
    if analyzer.is_fitted:
        print("\nSaving final results...")
        analyzer.save_cluster_datasets(analyzer.output_dir)
        analyzer.save_statistics(analyzer.output_dir)
        print(f"\nResults saved in: {analyzer.output_dir}")
    else:
        print("\nWarning: Model never fitted - no results to save")

    print("\nConfiguration complete.")

if __name__ == "__main__":
    main() 
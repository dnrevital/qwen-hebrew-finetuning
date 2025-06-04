import json
import csv
import re
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm
import os


def extract_faculty_from_marc(anies_field):
    """חילוץ פקולטה משדה MARC21"""
    if not anies_field:
        return "לא ידוע"

    # חפש שדה 710 (מוסדות) - פקולטה
    faculty_pattern = r'<datafield[^>]*tag="710"[^>]*>.*?<subfield code="b">(.*?)</subfield>'
    faculty_matches = re.findall(faculty_pattern, anies_field, re.DOTALL)

    if faculty_matches:
        return faculty_matches[0].strip()
    return "לא ידוע"


def get_pdf_size(json_path):
    """מצא את גודל קובץ ה-PDF הקשור"""
    try:
        # נתיב תיקיית המסמך
        parent_dir = json_path.parent

        # חפש תיקיות שאינן זהות לשם קובץ ה-JSON
        json_name = json_path.stem

        for item in parent_dir.iterdir():
            if item.is_dir() and item.name != json_name:
                # חפש קובץ PDF בתיקיה זו
                for pdf_file in item.glob("*.pdf"):
                    return pdf_file.stat().st_size

        return 0
    except Exception as e:
        print(f"Error reading PDF size for {json_path}: {e}")
        return 0


def process_json_file(json_path):
    """עיבוד קובץ JSON יחיד"""
    try:
        with open(json_path, 'r', encoding='utf-8') as file:
            raw_content = file.read()
            first_decode = json.loads(raw_content)
            data = json.loads(first_decode)

            # חלץ מידע בסיסי
            mms_id = data.get('mms_id', 'לא ידוע')
            title = data.get('title', 'לא ידוע')

            # חלץ פקולטה
            anies_content = data.get('anies', [''])[0] if data.get('anies') else ''
            faculty = extract_faculty_from_marc(anies_content)

            # קבל גודל PDF
            pdf_size = get_pdf_size(json_path)

            return {
                'ID': mms_id,
                'Title': title,
                'Faculty': faculty,
                'Size': pdf_size,
                'FilePath': str(json_path)
            }

    except Exception as e:
        print(f"Error processing {json_path}: {e}")
        return None


def collect_all_files(base_path):
    """אסוף את כל הקבצים מכל ה-parts"""
    base_dir = Path(base_path)
    all_files = []

    print("Collecting all JSON files...")

    for part_num in range(1, 18):  # part1 עד part17
        part_dir = base_dir / f"part{part_num}"

        if part_dir.exists():
            print(f"Scanning part{part_num}...")

            # מצא קבצי JSON בתיקיה
            json_files = []
            for item in part_dir.iterdir():
                if item.is_dir():
                    json_file = item / f"{item.name}.json"
                    if json_file.exists():
                        json_files.append(json_file)

            all_files.extend(json_files)
            print(f"Found {len(json_files)} files in part{part_num}")
        else:
            print(f"Directory {part_dir} not found")

    print(f"Total collected: {len(all_files)} files for processing")
    return all_files


def create_csv_with_stats(base_path, output_csv="document_analysis.csv", run_all=True):
    """יצירת CSV עם סטטיסטיקות"""

    # אסוף קבצים
    files_to_process = collect_all_files(base_path)

    if not files_to_process:
        print("No files found to process!")
        return

    # משתנים לסטטיסטיקות
    faculty_stats = defaultdict(lambda: {'count': 0, 'total_size': 0})
    total_documents = 0
    total_size = 0

    # רשימה לשמירת כל הנתונים
    all_documents = []

    print(f"\nProcessing {len(files_to_process)} files...")

    # עיבוד עם progress bar
    for json_file in tqdm(files_to_process, desc="Processing files"):
        result = process_json_file(json_file)

        if result:
            all_documents.append(result)

            # עדכן סטטיסטיקות
            faculty = result['Faculty']
            size = result['Size']

            faculty_stats[faculty]['count'] += 1
            faculty_stats[faculty]['total_size'] += size

            total_documents += 1
            total_size += size

    # כתיבת קובץ CSV
    print(f"\nWriting CSV file: {output_csv}")

    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['ID', 'Title', 'Faculty', 'Size']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for doc in all_documents:
            writer.writerow({
                'ID': doc['ID'],
                'Title': doc['Title'],
                'Faculty': doc['Faculty'],
                'Size': doc['Size']
            })

    # יצירת קובץ סטטיסטיקות נפרד
    stats_csv = "faculty_statistics.csv"
    print(f"\nWriting statistics to: {stats_csv}")

    with open(stats_csv, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['Faculty', 'Document_Count', 'Total_Size_MB']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for faculty, stats in sorted(faculty_stats.items(), key=lambda x: x[1]['total_size'], reverse=True):
            writer.writerow({
                'Faculty': faculty,
                'Document_Count': stats['count'],
                'Total_Size_MB': round(stats['total_size'] / (1024 * 1024), 2)
            })

        # הוסף שורת סיכום
        writer.writerow({
            'Faculty': 'Total',
            'Document_Count': total_documents,
            'Total_Size_MB': round(total_size / (1024 * 1024), 2)
        })


# שימוש
if __name__ == "__main__":
    base_path = r"G:\.shortcut-targets-by-id\1cErCnP4Phe-Supo0U_ju1u-KMunC6Et6\Tau All Data\aws"

    print("Starting FULL processing of all files...")
    create_csv_with_stats(base_path, "full_analysis.csv", run_all=True)
    print("\nFull processing completed!")
    print("Generated files:")
    print("- full_analysis.csv (document data)")
    print("- faculty_statistics.csv (faculty statistics)")
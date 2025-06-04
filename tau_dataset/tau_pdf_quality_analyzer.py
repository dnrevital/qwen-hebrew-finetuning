import pandas as pd
import PyPDF2
import fitz  # PyMuPDF - טוב יותר לטקסט
import re
import random
from pathlib import Path
from collections import Counter, defaultdict
from tqdm import tqdm
import json


class PDFQualityAnalyzer:
    def __init__(self, csv_path):
        """טוען את הנתונים הקיימים"""
        self.df = pd.read_csv(csv_path)
        self.sample_files = []
        self.analysis_results = []

    def create_representative_sample(self, sample_size=200):
        """יוצר מידגם מייצג של 200 קבצים"""
        print("Creating representative sample...")

        # מסנן רק קבצים שקיימים ובגודל מעל 100KB
        valid_files = self.df[self.df['Size'] > 100000].copy()

        # חלוקה לפי פקולטות (70% = 140 קבצים)
        faculty_samples = self._sample_by_faculty(valid_files, 140)

        # חלוקה לפי גודל (30% = 60 קבצים)
        size_samples = self._sample_by_size(valid_files, 60)

        # שילוב המידגמים (עם הסרת כפילויות)
        all_samples = pd.concat([faculty_samples, size_samples]).drop_duplicates(subset=['ID'])

        # אם יש יותר מ-200, נבחר רנדומלי
        if len(all_samples) > sample_size:
            all_samples = all_samples.sample(n=sample_size, random_state=42)

        # אם יש פחות מ-200, נוסיף עוד
        elif len(all_samples) < sample_size:
            remaining = sample_size - len(all_samples)
            additional = valid_files[~valid_files['ID'].isin(all_samples['ID'])].sample(n=remaining, random_state=42)
            all_samples = pd.concat([all_samples, additional])

        self.sample_files = all_samples
        print(f"Created sample of {len(self.sample_files)} files")

        return self.sample_files

    def _sample_by_faculty(self, df, target_count):
        """דגימה לפי פקולטות"""
        faculty_counts = df['Faculty'].value_counts()
        samples = []

        for faculty, count in faculty_counts.items():
            # חישוב כמה קבצים לקחת מהפקולטה (מינימום 3, מקסימום 25)
            faculty_sample_size = max(3, min(25, int(target_count * count / len(df))))

            faculty_files = df[df['Faculty'] == faculty]
            if len(faculty_files) >= faculty_sample_size:
                sample = faculty_files.sample(n=faculty_sample_size, random_state=42)
                samples.append(sample)

        return pd.concat(samples) if samples else pd.DataFrame()

    def _sample_by_size(self, df, target_count):
        """דגימה לפי גודל קובץ"""
        df = df.copy()
        df['Size_MB'] = df['Size'] / (1024 * 1024)

        # חלוקה לקטגוריות גודל
        small = df[df['Size_MB'] <= 5]
        medium = df[(df['Size_MB'] > 5) & (df['Size_MB'] <= 20)]
        large = df[df['Size_MB'] > 20]

        samples = []
        per_category = target_count // 3

        for category in [small, medium, large]:
            if len(category) >= per_category:
                sample = category.sample(n=per_category, random_state=42)
                samples.append(sample)

        return pd.concat(samples) if samples else pd.DataFrame()

    def analyze_pdf_quality(self, pdf_path):
        """ניתוח איכות PDF יחיד"""
        try:
            # פתיחת הקובץ
            doc = fitz.open(pdf_path)

            # חילוץ טקסט
            full_text = ""
            page_count = len(doc)

            for page_num in range(page_count):
                page = doc[page_num]
                text = page.get_text()
                full_text += text + "\n"

            doc.close()

            # ניתוח הטקסט
            analysis = {
                'file_path': str(pdf_path),
                'page_count': page_count,
                'total_chars': len(full_text),
                'total_words': len(full_text.split()),
                'text_sample': full_text[:500],  # דוגמא ראשונה
            }

            # חישוב ציונים
            analysis['technical_score'] = self._calculate_technical_score(full_text, pdf_path)
            analysis['structure_score'] = self._calculate_structure_score(full_text)
            analysis['content_score'] = self._calculate_content_score(full_text)
            analysis['overall_score'] = (analysis['technical_score'] +
                                         analysis['structure_score'] +
                                         analysis['content_score']) / 3

            # זיהוי בעיות
            analysis['issues'] = self._identify_issues(full_text)
            analysis['is_text_based'] = self._is_text_based(full_text, pdf_path)

            return analysis

        except Exception as e:
            return {
                'file_path': str(pdf_path),
                'error': str(e),
                'technical_score': 0,
                'structure_score': 0,
                'content_score': 0,
                'overall_score': 0,
                'is_text_based': False,
                'issues': [f"Failed to process: {e}"]
            }

    def _calculate_technical_score(self, text, pdf_path):
        """חישוב ציון טכני (0-100)"""
        score = 100

        # בדיקת קידוד (25 נקודות)
        if '�' in text or text.count('?') > len(text) * 0.01:
            score -= 25
        elif text.count('?') > len(text) * 0.005:
            score -= 10

        # בדיקת עברית (25 נקודות)
        hebrew_chars = len(re.findall(r'[\u0590-\u05FF]', text))
        total_chars = len([c for c in text if c.isalpha()])

        if total_chars > 0:
            hebrew_ratio = hebrew_chars / total_chars
            if hebrew_ratio > 0.3:  # מסמך עברי
                if hebrew_chars < 100:  # עברית חסרה
                    score -= 25
                elif text.count('?') > hebrew_chars * 0.1:  # הרבה סימני שאלה בעברית
                    score -= 15

        # בדיקת מבנה PDF (25 נקודות)
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                if len(pdf_reader.pages) == 0:
                    score -= 25
        except:
            score -= 25

        # בדיקת חילוץ טקסט (25 נקודות)
        if len(text.strip()) < 100:
            score -= 25
        elif len(text.split()) < 50:
            score -= 15

        return max(0, score)

    def _calculate_structure_score(self, text):
        """חישוב ציון מבנה (0-100)"""
        score = 100

        # בדיקת סדר לוגי (30 נקודות)
        lines = text.split('\n')
        empty_lines = sum(1 for line in lines if not line.strip())
        if empty_lines > len(lines) * 0.5:
            score -= 30
        elif empty_lines > len(lines) * 0.3:
            score -= 15

        # בדיקת כותרות חוזרות (25 נקודות)
        line_counts = Counter(lines)
        repeated_lines = [line for line, count in line_counts.items()
                          if count > 3 and len(line.strip()) > 10]
        if len(repeated_lines) > 5:
            score -= 25
        elif len(repeated_lines) > 2:
            score -= 10

        # בדיקת מספרי עמודים (20 נקודות)
        page_numbers = re.findall(r'^\s*\d+\s*$', text, re.MULTILINE)
        if len(page_numbers) > 10:
            score -= 20
        elif len(page_numbers) > 5:
            score -= 10

        # בדיקת פיצול מילים (25 נקודות)
        broken_words = re.findall(r'[\u0590-\u05FF]+-\s*\n\s*[\u0590-\u05FF]+', text)
        if len(broken_words) > 20:
            score -= 25
        elif len(broken_words) > 10:
            score -= 15

        return max(0, score)

    def _calculate_content_score(self, text):
        """חישוב ציון תוכן (0-100)"""
        score = 100

        # בדיקת רווחים (20 נקודות)
        multiple_spaces = len(re.findall(r' {3,}', text))
        if multiple_spaces > 50:
            score -= 20
        elif multiple_spaces > 20:
            score -= 10

        # בדיקת שורות שבורות (30 נקודות)
        broken_lines = len(re.findall(r'[א-ת]\s*\n\s*[א-ת]', text))
        if broken_lines > 100:
            score -= 30
        elif broken_lines > 50:
            score -= 15

        # בדיקת תווים מיוחדים (25 נקודות)
        special_chars = len(re.findall(r'[^\w\s\u0590-\u05FF.,!?;:\-()"]', text))
        if special_chars > len(text) * 0.05:
            score -= 25
        elif special_chars > len(text) * 0.02:
            score -= 10

        # בדיקת קוהרנטיות (25 נקודות)
        words = text.split()
        if len(words) > 0:
            avg_word_length = sum(len(word) for word in words) / len(words)
            if avg_word_length < 2 or avg_word_length > 15:
                score -= 25

        return max(0, score)

    def _identify_issues(self, text):
        """זיהוי בעיות ספציפיות"""
        issues = []

        # בעיות קידוד
        if '�' in text:
            issues.append("Corrupted characters (�)")

        # בעיות עברית
        hebrew_chars = len(re.findall(r'[\u0590-\u05FF]', text))
        question_marks = text.count('?')
        if hebrew_chars > 0 and question_marks > hebrew_chars * 0.1:
            issues.append("Hebrew encoding issues")

        # בעיות מבנה
        if len(re.findall(r' {5,}', text)) > 10:
            issues.append("Multiple spaces")

        if len(re.findall(r'\n\s*\n\s*\n', text)) > 20:
            issues.append("Multiple empty lines")

        # מספרי עמודים
        page_numbers = re.findall(r'^\s*\d+\s*$', text, re.MULTILINE)
        if len(page_numbers) > 10:
            issues.append("Page numbers in content")

        # שורות חוזרות
        lines = text.split('\n')
        line_counts = Counter(lines)
        repeated = [line for line, count in line_counts.items()
                    if count > 3 and len(line.strip()) > 10]
        if repeated:
            issues.append("Repeated headers/footers")

        return issues

    def _is_text_based(self, text, pdf_path):
        """בדיקה האם הקובץ מבוסס טקסט או צילום"""
        try:
            # בדיקה פשוטה: יחס מילים לגודל קובץ
            file_size = Path(pdf_path).stat().st_size
            word_count = len(text.split())

            if file_size == 0:
                return False

            words_per_mb = word_count / (file_size / (1024 * 1024))

            # אם יש פחות מ-500 מילים למגה - כנראה צילום
            return words_per_mb > 500

        except:
            return len(text.split()) > 100

    def run_analysis(self, base_path):
        """הרצת הניתוח על המידגם"""
        print("Starting PDF quality analysis...")

        results = []

        for idx, row in tqdm(self.sample_files.iterrows(), total=len(self.sample_files)):
            # בניית נתיב הקובץ
            pdf_path = self._build_pdf_path(base_path, row['ID'])

            if pdf_path and pdf_path.exists():
                analysis = self.analyze_pdf_quality(pdf_path)
                analysis['sample_id'] = row['ID']
                analysis['faculty'] = row['Faculty']
                analysis['file_size'] = row['Size']
                results.append(analysis)
            else:
                # קובץ לא נמצא
                results.append({
                    'sample_id': row['ID'],
                    'faculty': row['Faculty'],
                    'file_size': row['Size'],
                    'error': 'PDF file not found',
                    'technical_score': 0,
                    'structure_score': 0,
                    'content_score': 0,
                    'overall_score': 0,
                    'is_text_based': False
                })

        self.analysis_results = results
        return results

    def _build_pdf_path(self, base_path, file_id):
        """בניית נתיב לקובץ PDF"""
        base_dir = Path(base_path)

        # חיפוש בכל ה-parts
        for part_num in range(1, 18):
            part_dir = base_dir / f"part{part_num}"
            if part_dir.exists():
                doc_dir = part_dir / str(file_id)
                if doc_dir.exists():
                    # חיפוש PDF בתת-תיקיות
                    for subdir in doc_dir.iterdir():
                        if subdir.is_dir() and subdir.name != str(file_id):
                            pdf_files = list(subdir.glob("*.pdf"))
                            if pdf_files:
                                return pdf_files[0]

        return None

    def save_results(self, output_path="pdf_quality_analysis.csv"):
        """שמירת תוצאות לCSV"""
        if not self.analysis_results:
            print("No analysis results to save")
            return

        df_results = pd.DataFrame(self.analysis_results)
        df_results.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"Results saved to {output_path}")

        # הדפסת סיכום
        self.print_summary()

    def print_summary(self):
        """הדפסת סיכום התוצאות"""
        if not self.analysis_results:
            return

        df = pd.DataFrame(self.analysis_results)

        print("\n" + "=" * 60)
        print("PDF Quality Analysis Summary")
        print("=" * 60)

        # סטטיסטיקות כלליות
        total_files = len(df)
        text_based = df['is_text_based'].sum()

        print(f"Total files analyzed: {total_files}")
        print(f"Text-based files: {text_based} ({text_based / total_files * 100:.1f}%)")

        # ציונים ממוצעים
        avg_technical = df['technical_score'].mean()
        avg_structure = df['structure_score'].mean()
        avg_content = df['content_score'].mean()
        avg_overall = df['overall_score'].mean()

        print(f"\nAverage Scores:")
        print(f"Technical: {avg_technical:.1f}")
        print(f"Structure: {avg_structure:.1f}")
        print(f"Content: {avg_content:.1f}")
        print(f"Overall: {avg_overall:.1f}")

        # התפלגות ציונים
        print(f"\nScore Distribution:")
        print(f"Excellent (80+): {len(df[df['overall_score'] >= 80])}")
        print(f"Good (60-79): {len(df[(df['overall_score'] >= 60) & (df['overall_score'] < 80)])}")
        print(f"Fair (40-59): {len(df[(df['overall_score'] >= 40) & (df['overall_score'] < 60)])}")
        print(f"Poor (<40): {len(df[df['overall_score'] < 40])}")


# שימוש
if __name__ == "__main__":
    # נתיבים
    csv_path = "full_analysis.csv"  # הקובץ שיצרנו קודם
    base_path = r"G:\.shortcut-targets-by-id\1cErCnP4Phe-Supo0U_ju1u-KMunC6Et6\Tau All Data\aws"

    # יצירת האנליזר
    analyzer = PDFQualityAnalyzer(csv_path)

    # יצירת מידגם
    sample = analyzer.create_representative_sample(200)

    # הרצת הניתוח
    results = analyzer.run_analysis(base_path)

    # שמירת תוצאות
    analyzer.save_results("pdf_quality_analysis.csv")
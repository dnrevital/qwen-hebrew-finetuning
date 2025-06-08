#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import boto3
import pandas as pd
import json
from pathlib import Path
import re


def list_dikta_files(bucket_name, prefix):
    """
    מוצא את כל קבצי דיקטה-ויקיפדיה ב-S3
    """
    print(f"🔍 מחפש קבצי דיקטה ב-S3: {bucket_name}/{prefix}")
    print("=" * 60)

    s3 = boto3.client('s3')

    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        if 'Contents' not in response:
            print("❌ לא נמצאו קבצים")
            return []

        dikta_files = []
        for obj in response['Contents']:
            filename = obj['Key']
            # הקידומת כבר מכילה את AllOfNewHebrewWikipediaWithArticles
            if filename.startswith(prefix):
                size_mb = obj['Size'] / (1024 * 1024)
                dikta_files.append({
                    'filename': filename,
                    'size_mb': round(size_mb, 2),
                    'last_modified': obj['LastModified']
                })

        print(f"✅ נמצאו {len(dikta_files)} קבצי דיקטה-ויקיפדיה:")
        for i, file_info in enumerate(dikta_files, 1):
            print(f"   {i}. {file_info['filename']}")
            print(f"      גודל: {file_info['size_mb']} MB")
            print(f"      עדכון אחרון: {file_info['last_modified']}")
            print()

        return dikta_files

    except Exception as e:
        print(f"❌ שגיאה בגישה ל-S3: {e}")
        return []


def search_article_in_file(bucket_name, filename, article_title):
    """
    מחפש ערך ספציפי בקובץ דיקטה
    """
    print(f"🔍 מחפש '{article_title}' בקובץ: {filename}")

    s3 = boto3.client('s3')

    try:
        # הורדת הקובץ
        print(f"⬇️ מוריד קובץ...")
        local_filename = Path(filename).name
        s3.download_file(bucket_name, filename, local_filename)
        print(f"✅ הקובץ הורד: {local_filename}")

        # קריאת הקובץ (נניח שזה CSV)
        print(f"📖 קורא קובץ...")
        if filename.endswith('.csv'):
            df = pd.read_csv(local_filename)
            print(f"📊 נטען CSV עם {len(df)} שורות")
            print(f"📋 עמודות: {list(df.columns)}")

            # חיפוש הערך
            article_found = search_in_dataframe(df, article_title)
            return article_found

        elif filename.endswith('.json') or filename.endswith('.jsonl'):
            return search_in_json_file(local_filename, article_title)

        else:
            print(f"❓ פורמט קובץ לא מזוהה: {filename}")
            return None

    except Exception as e:
        print(f"❌ שגיאה בעיבוד קובץ {filename}: {e}")
        return None


def search_in_dataframe(df, article_title):
    """
    מחפש ערך ב-DataFrame על בסיס המילים הראשונות בטור text
    """
    print(f"🔎 מחפש '{article_title}' בטור text...")
    print(f"📊 הקובץ מכיל {len(df)} שורות")

    # וודא שיש טור text
    if 'text' not in df.columns:
        print(f"❌ לא נמצא טור 'text'. טורים זמינים: {list(df.columns)}")
        return None

    print(f"📋 טורים בקובץ: {list(df.columns)}")

    # חיפוש בטור text
    found_articles = []

    for idx, row in df.iterrows():
        text_content = str(row['text'])

        # בדיקה אם הטקסט מתחיל עם שם הערך
        if text_content.strip().startswith(article_title):
            found_articles.append((idx, text_content))
            print(f"✅ נמצא! שורה {idx}")
            print(f"📄 תחילת הטקסט: {text_content[:100]}...")

    if found_articles:
        # קח את הראשון שנמצא
        idx, content = found_articles[0]

        print(f"\n📝 תוכן הערך מלא:")
        print("=" * 60)
        print(content)
        print("=" * 60)

        # שמירת התוכן לקובץ
        output_filename = f"{article_title.replace(' ', '_')}_dikta.txt"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"💾 תוכן נשמר לקובץ: {output_filename}")

        # הצגת מידע נוסף על השורה
        if 'word_count' in df.columns:
            print(f"📊 מספר מילים: {row['word_count']}")
        if 'character_count' in df.columns:
            print(f"📊 מספר תווים: {row['character_count']}")
        if 'id' in df.columns:
            print(f"🆔 ID: {row['id']}")

        return content
    else:
        print(f"❌ לא נמצא ערך שמתחיל ב-'{article_title}'")

        # בדיקה אם יש ערכים דומים
        print(f"🔍 מחפש ערכים דומים...")
        similar_articles = []

        for idx, row in df.iterrows():
            text_content = str(row['text'])
            first_line = text_content.split('\n')[0].strip()

            # בדיקה אם יש מילים דומות
            if article_title.lower() in first_line.lower():
                similar_articles.append((idx, first_line))
                if len(similar_articles) >= 5:  # מקסימום 5 דוגמאות
                    break

        if similar_articles:
            print(f"💡 נמצאו ערכים דומים:")
            for idx, first_line in similar_articles:
                print(f"   שורה {idx}: {first_line[:80]}...")
        else:
            print(f"💡 לא נמצאו ערכים דומים")

        return None


def search_in_json_file(filename, article_title):
    """
    מחפש ערך בקובץ JSON
    """
    print(f"🔎 מחפש '{article_title}' בקובץ JSON: {filename}")

    try:
        # נסה JSON רגיל
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # חיפוש רקורסיבי
        result = search_in_json_recursive(data, article_title)
        if result:
            print(f"✅ נמצא ערך!")
            print(result[:500])
            return result

    except:
        # אם נכשל, נסה JSONL (JSON Lines)
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f):
                    if line.strip():
                        try:
                            obj = json.loads(line)
                            result = search_in_json_recursive(obj, article_title)
                            if result:
                                print(f"✅ נמצא בשורה {line_num}!")
                                return result
                        except:
                            continue
        except Exception as e:
            print(f"❌ שגיאה בקריאת JSON: {e}")

    return None


def search_in_json_recursive(obj, search_term):
    """
    חיפוש רקורסיבי ב-JSON
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and search_term in value:
                return value
            elif isinstance(value, (dict, list)):
                result = search_in_json_recursive(value, search_term)
                if result:
                    return result
    elif isinstance(obj, list):
        for item in obj:
            result = search_in_json_recursive(item, search_term)
            if result:
                return result

    return None


def main():
    """
    הפעלה ראשית
    """
    print("🎯 מוצא ערך ויקיפדיה מקבצי דיקטה")
    print("=" * 60)

    # הגדרות
    bucket_name = 'israllm-datasets'
    prefix = 'csv-dataset/AllOfNewHebrewWikipediaWithArticles'
    article_title = 'הבינום של ניוטון'

    print(f"🔍 מחפש ערך: '{article_title}'")
    print(f"📂 ב-S3: {bucket_name}/{prefix}")
    print()

    # שלב 1: מציאת קבצי דיקטה
    dikta_files = list_dikta_files(bucket_name, prefix)

    if not dikta_files:
        print("❌ לא נמצאו קבצי דיקטה")
        return

    # שלב 2: חיפוש בכל קובץ
    for file_info in dikta_files:
        filename = file_info['filename']
        print(f"\n{'=' * 60}")

        result = search_article_in_file(bucket_name, filename, article_title)

        if result:
            print(f"🎉 נמצא הערך '{article_title}' בקובץ: {filename}")
            break
    else:
        print(f"\n❌ הערך '{article_title}' לא נמצא באף קובץ דיקטה")
        print("💡 נסה ערכים אחרים או בדוק את שמות הקבצים")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import mwparserfromhell
import re
import bz2
from pathlib import Path


def find_article_in_dump(dump_path, article_title):
    """
    מוצא ערך ספציפי בדאמפ ויקיפדיא
    """
    print(f"🔍 מחפש ערך: '{article_title}' בדאמפ...")
    print(f"📂 דאמפ: {dump_path}")
    print("⏳ זה עלול לקחת זמן...")

    scanned_pages = 0

    with bz2.open(dump_path, 'rt', encoding='utf-8') as file:
        for event, elem in ET.iterparse(file, events=('start', 'end')):
            if event == 'end' and elem.tag.endswith('page'):
                scanned_pages += 1

                # הדפסת התקדמות כל 10,000 דפים
                if scanned_pages % 10000 == 0:
                    print(f"   סרקתי {scanned_pages:,} דפים...")

                # חילוץ הכותרת
                title_elem = elem.find('.//{*}title')
                if title_elem is not None and title_elem.text == article_title:

                    print(f"✅ נמצא ערך: '{article_title}' אחרי {scanned_pages:,} דפים!")

                    # חילוץ הטקסט
                    revision = elem.find('.//{*}revision')
                    text_elem = revision.find('.//{*}text') if revision is not None else None

                    if text_elem is not None and text_elem.text:
                        raw_wikitext = text_elem.text
                        print(f"📏 אורך ויקי-טקסט גולמי: {len(raw_wikitext):,} תווים")

                        elem.clear()
                        return raw_wikitext
                    else:
                        print(f"❌ לא נמצא תוכן בערך")
                        elem.clear()
                        return None

                elem.clear()

    print(f"❌ לא נמצא ערך: '{article_title}' (סרקתי {scanned_pages:,} דפים)")
    return None


def normalize_text_for_training(text):
    """
    נרמול טקסט (בדיוק כמו בתוכנית הראשית)
    """
    if not text or not isinstance(text, str):
        return text

    # תיקון תווי בריחה לפני הכל
    text = text.replace('\\"', '"')
    text = text.replace("\\'", "'")
    text = text.replace('\\\\', '\\')

    # תיקון גם וריאציות של תווי בריחה
    text = text.replace('&quot;', '"')
    text = text.replace('&#34;', '"')
    text = text.replace('&#39;', "'")

    # מחק שורות חדשות ו-\r
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    text = text.replace('\t', ' ')

    # מחק תווי בריחה שנשארו
    text = text.replace('\\n', ' ')
    text = text.replace('\\t', ' ')
    text = text.replace('\\r', ' ')

    # רווחים מרובים → רווח יחיד
    text = re.sub(r'\s+', ' ', text)

    # נקה רווחים בהתחלה/סוף
    text = text.strip()

    return text


def process_with_our_method(raw_wikitext):
    """
    עיבוד עם השיטה שלנו (בדיוק כמו בתוכנית הראשית)
    """
    print(f"⚙️ מעבד את הויקי-טקסט...")

    try:
        wikicode = mwparserfromhell.parse(raw_wikitext)
        print(f"✅ ויקי-טקסט נותח בהצלחה")
    except Exception as e:
        print(f"❌ שגיאה בניתוח ויקי-טקסט: {e}")
        # fallback לטקסט גולמי
        return normalize_text_for_training(raw_wikitext[:1000])

    # הסרת תבניות
    print(f"🧹 מסיר תבניות...")
    templates_to_remove = []
    for template in wikicode.filter_templates():
        template_name = str(template.name).strip().lower()

        # אל תסיר תבניות מתמטיות חשובות
        if template_name in ['math', 'מתמטיקה', 'נוסחה']:
            continue

        # תבניות להסרה מלאה
        remove_patterns = [
            'cite', 'צ-', 'הערה', 'מקור', 'reflist', 'מקורות',
            'ציון', 'ref', 'citation', 'web', 'news', 'book', 'journal'
        ]
        if any(pattern in template_name for pattern in remove_patterns):
            templates_to_remove.append(template)

    # הסרת התבניות
    for template in templates_to_remove:
        try:
            wikicode.remove(template)
        except:
            pass

    print(f"✅ הוסרו {len(templates_to_remove)} תבניות")

    # המרת קישורים פנימיים לטקסט
    print(f"🔗 מעבד קישורים...")
    links_processed = 0
    for link in wikicode.filter_wikilinks():
        try:
            if link.text:
                wikicode.replace(link, str(link.text))
            else:
                title = str(link.title)
                if '|' in title:
                    title = title.split('|')[0]
                wikicode.replace(link, title)
            links_processed += 1
        except:
            pass

    print(f"✅ עובדו {links_processed} קישורים")

    # טיפול בתגיות מיוחדות
    print(f"🏷️ מעבד תגיות...")
    math_tags = 0
    for tag in wikicode.filter_tags():
        try:
            if tag.tag.lower() in ['math', 'chem']:
                # שמירת הנוסחה עם סימון מיוחד - בדיוק כמו במדגם
                wikicode.replace(tag, f"[נוסחה: {tag.contents}]")
                math_tags += 1
            elif tag.tag.lower() in ['ref', 'references']:
                wikicode.remove(tag)
        except:
            pass

    print(f"✅ נמצאו {math_tags} נוסחאות מתמטיות")

    # המרת הכל לטקסט
    content = str(wikicode.strip_code())
    print(f"📄 אורך אחרי המרה לטקסט: {len(content):,} תווים")

    # ניקוי regex
    print(f"🧽 מבצע ניקוי regex...")
    # הסרת תבניות שנשארו
    content = re.sub(r'\{\{[^}]*\}\}', '', content)
    # הסרת קישורים שנשארו
    content = re.sub(r'\[\[[^]]*\]\]', '', content)
    # הסרת תגיות HTML
    content = re.sub(r'<[^>]*>', '', content)

    # הסרת תיאורי תמונות ומדיה
    content = re.sub(r'^(שמאל|ימין|מרכז|ממוזער)\|.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*(שמאל|ימין|מרכז|ממוזער)\|.*$', '', content, flags=re.MULTILINE)

    # הסרת הסברי שפות זרות בסוגריים
    foreign_languages = ['בגרמנית', 'בהונגרית', 'בערבית', 'בכורדית', 'באנגלית',
                         'בצרפתית', 'באיטלקית', 'ברוסית', 'ביוונית', 'בלטינית']
    for lang in foreign_languages:
        pattern = r'\(' + lang + r':.*?\)'
        content = re.sub(pattern, '', content)

    # הסרת הפניות לתמונות
    content = re.sub(r'ראו [A-Za-z\s,]+\.', '', content)

    # ניקוי כללי
    content = re.sub(r'\n{3,}', '\n\n', content)  # שורות ריקות מרובות
    content = re.sub(r' {2,}', ' ', content)  # רווחים מרובים
    content = re.sub(r'^\s*=+.*?=+\s*$', '', content, flags=re.MULTILINE)  # כותרות ויקי

    print(f"📄 אורך אחרי ניקוי regex: {len(content):,} תווים")

    # זיהוי כותרות (פשוט)
    print(f"📋 מזהה כותרות...")
    content = identify_headers(content)

    # נרמול הטקסט לאימון
    print(f"🔄 מנרמל טקסט...")
    content = normalize_text_for_training(content)

    print(f"✅ אורך סופי: {len(content):,} תווים")

    return content


def identify_headers(content):
    """
    זיהוי וסימון כותרות (בדיוק כמו בתוכנית הראשית)
    """
    lines = content.split('\n')
    processed_lines = []
    headers_found = 0

    for i, line in enumerate(lines):
        line = line.strip()

        # זיהוי כותרת פשוט
        if (line and len(line) < 100 and
                i < len(lines) - 1 and
                len(lines[i + 1].strip()) > 50 and
                line.count('.') <= 1 and
                line.count(',') <= 2):

            # בדיקות נוספות לוודא שזו כותרת
            header_keywords = ['היסטוריה', 'ביוגרפיה', 'רקע', 'תולדות', 'מוצא', 'תרבות', 'משפחתו', 'ילדותו', 'נעוריו',
                               'התפתחות', 'משימות']
            if (not line.endswith('.') or
                    any(keyword in line for keyword in header_keywords)):
                processed_lines.append(f"## {line}")
                headers_found += 1
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)

    print(f"✅ זוהו {headers_found} כותרות")
    return '\n'.join(processed_lines)


def main():
    """
    הפעלה ראשית
    """
    print("🎯 מוצא ומעבד ערך מהדאמפ שלנו")
    print("=" * 60)

    # הגדרות
    dump_path = r'C:\Users\Dan Revital\OneDrive\Documents\gepeta\data\wikipedia\hewiki-latest-pages-articles.xml.bz2'
    article_title = 'הבינום של ניוטון'

    print(f"🔍 מחפש ערך: '{article_title}'")
    print(f"📂 בדאמפ: {dump_path}")
    print()

    # שלב 1: מציאת הערך
    raw_wikitext = find_article_in_dump(dump_path, article_title)

    if not raw_wikitext:
        print(f"❌ לא נמצא הערך '{article_title}'")
        return

    print()

    # שלב 2: עיבוד עם השיטה שלנו
    print("=" * 60)
    processed_content = process_with_our_method(raw_wikitext)

    # שלב 3: שמירת התוצאות
    print("=" * 60)
    print("💾 שומר תוצאות...")

    # שמירת הטקסט הגולמי
    raw_filename = f"{article_title.replace(' ', '_')}_raw_wikitext.txt"
    with open(raw_filename, 'w', encoding='utf-8') as f:
        f.write(raw_wikitext)
    print(f"✅ ויקי-טקסט גולמי נשמר: {raw_filename}")

    # שמירת הטקסט המעובד
    processed_filename = f"{article_title.replace(' ', '_')}_our_processed.txt"
    with open(processed_filename, 'w', encoding='utf-8') as f:
        f.write(processed_content)
    print(f"✅ טקסט מעובד נשמר: {processed_filename}")

    # סיכום
    print("\n" + "=" * 60)
    print("🎉 הושלם בהצלחה!")
    print(f"📊 סיכום:")
    print(f"   ויקי-טקסט גולמי: {len(raw_wikitext):,} תווים")
    print(f"   טקסט מעובד: {len(processed_content):,} תווים")
    print(f"   דחיסה: {(1 - len(processed_content) / len(raw_wikitext)) * 100:.1f}%")

    print(f"\n📄 דוגמה מהטקסט המעובד (200 תווים ראשונים):")
    print(f"   {processed_content[:200]}...")

    print(f"\n💡 עכשיו תוכל להשוות עם הקובץ:")
    print(f"   {article_title.replace(' ', '_')}_dikta.txt")


if __name__ == "__main__":
    main()
import re

# Special codes and abbreviations to remove
CODES_TO_REMOVE = [
    'מלמ', 'מלמ״ח', 'מלמ"ח',
    # Add more codes here
]

# Common Hebrew months
HEBREW_MONTHS = [
    'ינואר', 'פברואר', 'מרץ', 'מרס', 'אפריל', 'מאי', 'יוני',
    'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
    'ניסן', 'אייר', 'סיון', 'תמוז', 'אב', 'אלול',
    'תשרי', 'חשון', 'כסלו', 'טבת', 'שבט', 'אדר'
]

# Hebrew abbreviations mapping
ABBREVIATIONS_MAPPING = {
    'אדמו"ר': 'אדמור',
    'בע"ה': 'בעזרת השם',
    'צה"ל': 'צבא הגנה לישראל',
    # Add more abbreviations here
}

# Text cleaning configuration
MIN_WORD_LENGTH = 4
MAX_WORD_LENGTH = 20
MIN_HEBREW_CHARS_RATIO = 0.7  # Minimum ratio of Hebrew characters in a word

# TF-IDF configuration
TFIDF_CONFIG = {
    'max_features': 10000,
    'min_df': 2,        # Appear in at least 2 documents
    'max_df': 0.7,      # Appear in at most 70% of documents
}

# Hebrew character pattern
HEBREW_PATTERN = re.compile(r'[\u0590-\u05FF\uFB1D-\uFB4F]')

def is_mostly_hebrew(text):
    """Check if text contains mostly Hebrew characters."""
    if not text:
        return False
    hebrew_chars = len(HEBREW_PATTERN.findall(text))
    return hebrew_chars / len(text) >= MIN_HEBREW_CHARS_RATIO

def is_date_related(word):
    """Check if word is related to dates."""
    return word in HEBREW_MONTHS 
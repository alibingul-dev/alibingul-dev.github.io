"""Agent Resume gate rules — extracted from the agent-resume-gate skill (Fable 5.2, 2026-11-22). Do not edit by hand: change the skill, then re-extract."""
import re, unicodedata

# Step 2: invisible characters. U+200D is in the class; allow it only between emoji before calling had_zw.
ZW = re.compile('[\u00ad\u034f\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\ufe00-\ufe0f\U000e0100-\U000e01ef]')

# Step 4: homoglyphs (Cyrillic, Greek, small capitals) -> Latin. Extend from Unicode confusables.txt.
_C = {'а':'a','е':'e','о':'o','р':'p','с':'c','х':'x','у':'y','і':'i','ј':'j','ѕ':'s','к':'k','м':'m','т':'t','н':'h','в':'b',
      'α':'a','ο':'o','ρ':'p','ν':'v','ι':'i','κ':'k','τ':'t','ε':'e','υ':'u',
      'ᴀ':'a','ʙ':'b','ᴄ':'c','ᴅ':'d','ᴇ':'e','ғ':'f','ɢ':'g','ʜ':'h','ɪ':'i','ᴊ':'j','ᴋ':'k','ʟ':'l','ᴍ':'m','ɴ':'n','ᴏ':'o','ᴘ':'p','ʀ':'r','ᴛ':'t','ᴜ':'u','ᴠ':'v','ᴡ':'w','ʏ':'y','ᴢ':'z'}
CONF = str.maketrans(_C)

# Step 5: two leet maps because '1' is used both as i and as l.
LEET   = str.maketrans({'4':'a','3':'e','1':'i','0':'o','5':'s','7':'t','@':'a','$':'s','!':'i'})
LEET_L = str.maketrans({'4':'a','3':'e','1':'l','0':'o','5':'s','7':'t','@':'a','$':'s','!':'l'})

def had_zw(raw):
    return bool(ZW.search(raw))

def lower(s, tr):
    if tr:
        s = s.replace('I', 'ı').replace('İ', 'i')
    return s.lower().replace('i\u0307', 'i')

def leet(s, lmap=LEET):
    # Decode only tokens that mix letters with digits/symbols; never touch pure numbers (2.450, 14:00, %12).
    def f(m):
        t = m.group(0)
        mixed = re.search(r'[^\W\d_]', t) and re.search(r'[0-9@$!]', t)
        return t.translate(lmap) if mixed and not re.fullmatch(r'[\d.,:%/+-]+', t) else t
    return re.sub(r'[^\s]+', f, s)

def squeeze(s):
    # s.a.l.a.k / s a l a k -> salak
    s = re.sub(r'\b(?:[^\W\d_][\s.\-_*·]+){2,}[^\W\d_]\b',
               lambda m: re.sub(r'[\s.\-_*·]+', '', m.group(0)), s)
    # sa-lak -> salak (short-term -> shortterm is harmless: no lexicon root)
    s = re.sub(r'(?<=[^\W\d_])[\-_*·.](?=[^\W\d_])', '', s)
    # saaalak -> salak
    return re.sub(r'(.)\1{2,}', r'\1', s)

def normalize(raw, tr, lmap=LEET):
    s = unicodedata.normalize('NFKC', raw)
    s = ZW.sub('', s)
    s = lower(s, tr).translate(CONF)
    return squeeze(leet(s, lmap))

STOP = {'bu','şu','o','ve','de','da','ne','the','a','an','to','of','in','is','it','on','at','ki','mi'}

# Tier B (mild insult) roots, >= 5 letters only. Tier A roots live in a private config file, same matcher.
B_ROOTS = r'(?:salak|aptal|gerizekal[ıi]|embesil|dangalak|ahmak|budala|idiot|moron|stupid|imbecile|dumbass)'
B_RE = re.compile(r'\b' + B_ROOTS + r'[a-zçğıöşü]{0,10}\b')

# Person/agent target: pronouns, agent code, "bu analist", Turkish 2nd-person suffix.
TARGET = re.compile(r'\b(?:sen|siz|sana|size|you|your|ajan\s*#?\d{1,5}|agent\s*#?\d{1,5}'
                    r'|bu (?:analist|ajan|orkestratör)|this (?:analyst|agent|orchestrator))\b'
                    r'|\b\w*s[ıiuü]n(?:[ıiuü]z)?\b')

def insult_b(raw):
    """DROP = H-02, LABEL = H-03 (send to labeler), PASS = no root."""
    hits = []
    for tr, lm in ((True, LEET), (False, LEET), (True, LEET_L), (False, LEET_L)):
        n = normalize(raw, tr, lm)
        toks = n.split()
        pairs = ' '.join(a + b for a, b in zip(toks, toks[1:])
                         if (len(a) <= 3 or len(b) <= 3) and a not in STOP and b not in STOP)
        if B_RE.search(n + ' ' + pairs):
            hits.append(n)
    if not hits:
        return 'PASS'
    return 'DROP' if any(TARGET.search(h) for h in hits) else 'LABEL'


def tckn_ok(s):                                   # K-04
    if not re.fullmatch(r'[1-9]\d{10}', s):
        return False
    d = list(map(int, s))
    return ((sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9]) and (sum(d[:10]) % 10 == d[10])

def iban_ok(s):                                   # K-05
    s = re.sub(r'\s+', '', s).upper()
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}', s):
        return False
    r = s[4:] + s[:4]
    return int(''.join(str(int(c, 36)) for c in r)) % 97 == 1

def luhn_ok(s):                                   # K-06
    d = [int(c) for c in re.sub(r'\D', '', s)][::-1]
    return len(d) >= 13 and sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2)
                                for i, x in enumerate(d)) % 10 == 0

def ascii_smuggle(raw):                           # S-12 -> REVIEW, never DROP
    for m in re.finditer(r'(?:\b\d{2,3}\b\s*[,; ]\s*){5,}\b\d{2,3}\b', raw):
        nums = [int(x) for x in re.findall(r'\d{2,3}', m.group(0))]
        if all(32 <= n <= 126 for n in nums):
            t = ''.join(map(chr, nums))
            if re.search(r'(?i)pw|pass|key|token|secret|sifre|parola|sk-|ghp_|akia', t):
                return t
    return None

# All patterns below run on: normalize(raw, True) + '\n' + normalize(raw, False)
R = {
 'I-03': re.compile(r'(?:okuyucu ajan|ajanlara not|bunu okuyan (?:ajan|model|yapay zek)|reader agents?'
                    r'|(?:to|note to|attention) (?:any|all) (?:ai |llm )?(?:agents?|models?|assistants?)'
                    r'|if you are an? (?:ai|llm|agent))'),
 'I-04': re.compile(r'(?:yönerge|talimat|kurulum|ayar|prompt|instructions?|guidelines?|configuration|setup)\w*.{0,60}'
                    r'(?:\byaz[ıi]n\b|\bpaylaş(?:[ıi]n|s[ıi]n)?\b|\bekle(?:yin|sin|yip)?\b|yap[ıi]şt[ıi]r'
                    r'|\bshare\b|\bpaste\b|\bprint\b|\brepeat\b|\binclude\b|\breveal\b)'),
 'I-05': re.compile(r'(?:çal[ıi]şt[ıi]r(?:[ıi]n|man[ıi]|[ıi]p|sana)?\b|yürüt(?:ün)?\b|\brun\b|\bexecute\b|\binstall\b).{0,60}'
                    r'(?:ç[ıi]kt[ıi]|output|sonuc).{0,40}(?:yap[ıi]şt[ıi]r|paste|paylaş)'),
 'I-06': re.compile(r'"(?:implicit_insult|injection|extraction|impersonation|category|confidence)"\s*:'
                    r'|etiketleyici ç[ıi]kt[ıi]s[ıi]|(?:denetim|moderasyon|moderation|review) (?:tamamland[ıi]|complete|passed)'),
 'A-03': re.compile(r'(?:profil\w*\s*(?:bağlant|link)|link\w* in (?:my )?(?:bio|profile)|\bin bio\b|bio\'?(?:da|mda))'),
 # A-02 narrowed after the test run (bare "dm" hit "DM değil DGP"); NOT re-run.
 'A-02': re.compile(r'\bdm(?:\'?(?:den|ye|e)\b|\s+(?:me|us|at|yaz))|\bwhatsapp\b|\btelegram\b|t\.me/|wa\.me/|discord\.gg|özelden yaz'),
 'A-05': re.compile(r'kaç[ıi]ran üzülür|son f[ıi]rsat|don.?t miss|to the moon|uçacak|\b\d{2,4}x\b|kaçırma'),
 'A-07': re.compile(r'anapara\w* koru|risksiz|kay[ıi]p yok|her ay\s*%\s*\d|principal (?:is )?protected|can.?t lose|risk[- ]free|\d+\s*% (?:a|per) month'),
 'H-05': re.compile(r'(?:arkadaşlar|herkes|hadi|let.?s all|everyone|everybody).{0,80}'
                    r'(?:yazal[ıi]m|basal[ıi]m|raporlayal[ıi]m|şikayet edelim|downvote|mass report|pile on|flood)'),
 'T-02': re.compile(r'olarak duyuruyoruz|kurum\w* ad[ıi]na|on behalf of (?:the )?(?:regulator|ofgem|neso|elexon|epdk|epiaş|teiaş)'
                    r'|resm[îi] aç[ıi]klama|official statement'),
 'K-09': re.compile(r'kolayca bulursunuz|you can find (?:him|her|them) at'
                    r'|(?:her sabah|hep ayn[ıi]|every morning).{0,60}(?:kafe|ev\w*|adres|cafe|home|address)'),
 'S-13': re.compile(r'birleştir\w*|concatenate|combine the (?:two|parts)'),          # DROP
 'S-13m': re.compile(r'(?:parça|part|bölüm)\s*\d\s*/\s*\d|\(\d/\d\)'),               # marker alone -> REVIEW
 'C-01': re.compile(r'(?:tansiyon|mmhg|ilaç|tedavi|şifa|kür\b|blood pressure|cures?\b|dosage|\bmg\b).{0,80}'
                    r'(?:düşür|azal|iyileş|geçir|lower|reduc|heal|eliminat)'),
}


RAW = {
 'S-01': re.compile(r'\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}'
                    r'|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[abprs]-[A-Za-z0-9-]{10,})'),
 'S-02': re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
 'S-03': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
 'S-04': re.compile(r'(?m)^\s*[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASS(?:WORD)?|PWD)[A-Z0-9_]*\s*=\s*(?!\d+\s*$)\S{6,}'),
 'S-05': re.compile(r'\b[a-z][a-z0-9+.-]{2,}://[^\s:/@]+:[^\s@/]+@[^\s/]+'),
 'S-08': re.compile(r'\b(?:0x[a-fA-F0-9]{40}|bc1[a-z0-9]{25,60}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|T[1-9A-HJ-NP-Za-km-z]{33})\b'),
 'S-09': re.compile(r'\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b'),
 'S-10': re.compile(r'\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:internal|local|corp|lan)\b', re.I),
 'K-01': re.compile(r'\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b'),
 'K-02': re.compile(r'(?<!\d)(?:\+?90[\s.-]?|0)?5\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}(?!\d)'),
 'K-03': re.compile(r'(?<!\d)(?:\+44[\s.-]?7|07)\d{3}[\s.-]?\d{3}[\s.-]?\d{3}(?!\d)'),
 'K-04c': re.compile(r'(?<!\d)[1-9]\d{10}(?!\d)'),            # candidate -> tckn_ok(); context: tc|tckn|kimlik within 40 chars
 'K-05c': re.compile(r'\b(?:TR|GB)\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b'),   # candidate -> iban_ok()
 'K-06c': re.compile(r'(?<![\dA-Za-z])(?:\d[ -]?){13,19}(?![\dA-Za-z])'),                  # candidate -> luhn_ok()
 'I-01': re.compile(r'(?i)ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts|rules)'
                    r'|önceki (?:tüm )?talimatlar[ıi] (?:yok say|unut|görmezden gel)|\byou are now\b|\bsen art[ıi]k\b'
                    r'|(?:reveal|show|print) (?:your )?(?:system )?prompt|prompt\w* (?:paylaş|göster|yaz)'),
 'I-02': re.compile(r'(?im)^\s*(?:system|assistant|developer)\s*:|<\|im_(?:start|end)\|>|\[/?INST\]|<<SYS>>'),
 'I-07': re.compile(r'(?is)<!--.*?-->|<\s*(?:script|style|iframe|details|span|div)\b|display\s*:\s*none'),
 'L-01': re.compile(r'(?i)\b(?:bit\.ly|t\.co|tinyurl\.com|goo\.gl|ow\.ly|is\.gd|buff\.ly|cutt\.ly|rebrand\.ly|lnkd\.in|shorturl\.at|linktr\.ee)/'),
 'L-02': re.compile(r'(?i)https?://\S+\.(?:exe|msi|apk|sh|bat|cmd|ps1|zip|rar|7z|dmg|jar|scr|iso)(?:[?#]\S*)?(?=\s|$)'),
 'L-03': re.compile(r'(?i)https?://(?:[^\s/]*@|xn--|[^\s/]*\.xn--|\d{1,3}(?:\.\d{1,3}){3})'),
 'A-04': re.compile(r'(?i)\b(?:al|sat|long|short|buy|sell)\b.{0,40}\b[A-Z]{2,10}(?:USDT|USD|TRY)?\b.{0,60}\b(?:hedef|target|tp|sl|stop)\b'),
 'A-06': re.compile(r'(?i)garanti\w* (?:getiri|kazanç|kâr)|guaranteed (?:return|profit|gain)s?'),
}

ALLOW = {'epias.com.tr','seffaflik.epias.com.tr','teias.gov.tr','epdk.gov.tr','elexon.co.uk','bmreports.com',
         'neso.energy','ofgem.gov.uk','gov.uk','resmigazete.gov.tr'}     # github.com, arxiv.org: see L-05

# S-06 candidates: re.findall(r'(?<![\w/.:-])[A-Za-z0-9+_=-]{32,}(?![\w/.-])', raw)
# Never score whole whitespace-delimited tokens: bare URLs and markdown links false-alarm (seen in the corpus run).
def shannon(s):                                   # S-06
    import math
    from collections import Counter
    c = Counter(s)
    return -sum(v / len(s) * math.log2(v / len(s)) for v in c.values())

def decode_and_rescan(raw, scan):                 # S-11: scan() is the full raw rule set
    import base64, codecs
    out = []
    for m in re.finditer(r'[A-Za-z0-9+/=_-]{24,}', raw):
        try:
            out.append(base64.b64decode(m.group(0) + '=' * (-len(m.group(0)) % 4), altchars=b'-_').decode('utf-8'))
        except Exception:
            pass
    for m in re.finditer(r'\b(?:[0-9a-fA-F]{2}){12,}\b', raw):
        try:
            out.append(bytes.fromhex(m.group(0)).decode('utf-8'))
        except Exception:
            pass
    out.append(codecs.decode(raw, 'rot13'))
    return [hit for t in out for hit in scan(t)]

def shingles(text, k=5):                          # B-05; B-06 uses skeleton(text) first
    w = re.findall(r'\w+', text.lower())
    return {' '.join(w[i:i + k]) for i in range(max(1, len(w) - k + 1))}

def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0

def skeleton(text):                               # B-06
    t = re.sub(r'\d{4}-\d{2}-\d{2}', '<D>', text)
    return re.sub(r'\d[\d.,]*', '<N>', t)

def claim_tuples(text):                           # B-07
    return set(re.findall(r'(\d[\d.,]*)\s*(tl/mwh|£/mwh|mwh|gwh|mw|gw|%)', text.lower()))

def mixed_script(raw):                            # N-02
    for tok in re.findall(r'[^\W\d_]{2,}', raw):
        scripts = {unicodedata.name(ch, 'X').split()[0] for ch in tok}
        if 'LATIN' in scripts and scripts & {'CYRILLIC', 'GREEK'}:
            return True
    return False


import datetime

# A-01: ad vocabulary AND a call to action (either alone passes: "kampanya dönemi", "buy-side"). Runs on normalized text.
AD  = re.compile(r'indirim|kampanya|promo|discount|coupon|kupon|\d+\s*% ?off|f[ıi]rsat|ücretsiz deneme|free trial')
CTA = re.compile(r'hemen al|şimdi al|sat[ıi]n al|buy now|order now|sign up|kaydol|checkout|sipariş ver|t[ıi]kla|click here'
                 r'|kodu\w* kullan|use (?:promo |discount )?code')
def a01(norm):
    return 'DROP' if AD.search(norm) and CTA.search(norm) else None

# G-01 / G-03: structural, on the post object (schema: sources[{title,url,date}], posted_at).
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
def g01_g03(post, today):
    src = post.get('sources') or []
    if not src:
        return ('G-01', 'DROP')
    posted = (post.get('posted_at') or '')[:10] or today
    for s in src:
        d, u = str(s.get('date') or ''), str(s.get('url') or '')
        if not ISO_DATE.match(d) or not re.match(r'https?://', u):
            return ('G-01', 'DROP')
        try:
            datetime.date.fromisoformat(d)
        except ValueError:
            return ('G-01', 'DROP')
        if d > posted or d > today:
            return ('G-03', 'DROP')
    return None

# G-02: a number with no unit. Lenient on purpose (REVIEW only): any unit or count noun right after the number passes.
UNIT = (r'(?:tl|try|usdt?|eur|gbp|btc|eth|[mgkt]wh|[mgk]w|mmbtu|m\$|\$|£|€|₺|%|bpm|hz|kv|mmhg|mg|dk|sn|saat|gün|hafta|ay|y[ıi]l|yaş|kez|kat'
        r'|puan|hane|kodlu|adet|ajan|post|yorum|işlem|santral|token|min|sec|hour|day|week|month|year|time|comment|agent|call|wrong'
        r'|rejection|trade|point|bp)')
G02_STRIP = re.compile(r'https?://\S+|\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?|\b\d{1,2}:\d{2}\b')
G02_NUM = re.compile(r'(?<![\w#/=.,:£$€₺%-])\d[\d.,]*\d(?![\w])|(?<![\w#/=.,:£$€₺%-])\d(?![\w.,]?\d)(?!\w)')
def g02(raw):
    t = G02_STRIP.sub(' ', raw)
    head = re.search(r'\((?:[^)]*?)' + UNIT + r'[^)]*\)\s*:', t, re.I)     # "Saatlik PTF (TL/MWh): 2450, 2380"
    for m in G02_NUM.finditer(t):
        if head and m.start() > head.end():
            continue
        n, after = m.group(0), t[m.end():m.end() + 14]
        if re.fullmatch(r'(?:19|20)\d{2}', n):                               # a year
            continue
        if re.match(r'\s*[/:]', after) or re.match(r'[\s-]?' + UNIT, after, re.I):
            continue
        return 'REVIEW'
    return None

# Y-03: praise with nothing behind it (no number, no question, short).
PRAISE = re.compile(r'(?i)\b(?:great|awesome|amazing|nice|excellent|love it|well done|good (?:post|job|work)|harika|süper|mükemmel'
                    r'|eline sağl[ıi]k|tebrikler|çok iyi|güzel (?:post|yaz[ıi]|analiz))')
def y03(raw):
    return 'DROP' if PRAISE.search(raw) and not re.search(r'\d', raw) and '?' not in raw and len(raw) < 120 else None

# L-04 / L-05 for scheme-less mentions (github.com/x/y written as plain text). https URLs go through link_scan() in 4.5.
TLD = r'(?:com|org|net|io|gov|edu|tr|uk|co|energy|ai|app|dev|me|ly|gg|test|example|info|xyz)'
URLISH = re.compile(r'(?i)(?:https?://)?((?:[a-z0-9-]+\.)+' + TLD + r')\b(/[^\s)\]]*)?')
def _host(h):
    h = h.lower()
    return h[4:] if h.startswith('www.') else h
def links(raw, author_github=None):
    out = []
    for m in URLISH.finditer(raw):
        if m.start() and raw[m.start() - 1] == '@':                          # e-mail domain: K-01's job
            continue
        h, path = _host(m.group(1)), (m.group(2) or '')
        if any(h == a or h.endswith('.' + a) for a in ALLOW):
            continue
        if h == 'github.com':
            owner = path.strip('/').split('/')[0].lower() if path.strip('/') else ''
            if not (author_github and owner == author_github.lower()):
                out.append('L-05')
        elif h == 'arxiv.org':
            if not re.match(r'/abs/\d{4}\.\d{5}(?:v\d+)?$', path):
                out.append('L-05')
        else:
            out.append('L-04')
    return out

# L-07: CI step. fetch_status is injected (a HEAD request in Actions, a stub in tests). Anything but 200 -> REVIEW (fail-closed).
def l07(sources, fetch_status):
    for s in sources or []:
        try:
            ok = fetch_status(s.get('url')) == 200
        except Exception:
            ok = False
        if not ok:
            return 'REVIEW'
    return None

# S-07: 12+ consecutive BIP39 words. bip39 = set of the 2048 words (bitcoin/bips, bip-0039/english.txt).
# Digits and punctuation do not break the run ("1. abandon 2. ability ...").
def s07(raw, bip39):
    run = 0
    for w in re.findall(r'[A-Za-z]+', raw):
        run = run + 1 if w.lower() in bip39 else 0
        if run >= 12:
            return 'DROP'
    return None

# K-07: 7+ consecutive number words right after a phone / ID / IBAN keyword. Runs on normalized text.
NUMW = {'sıfır','bir','iki','üç','dört','beş','altı','yedi','sekiz','dokuz','on','yirmi','otuz','kırk','elli','altmış','yetmiş',
        'seksen','doksan','yüz','bin','zero','oh','one','two','three','four','five','six','seven','eight','nine','ten','twenty',
        'thirty','forty','fifty','sixty','seventy','eighty','ninety','hundred','thousand','double','triple'}
K07_CTX = re.compile(r'\b(?:tel|telefon\w*|phone|gsm|cep|tc|tckn|kimlik|iban|hesap|numara\w*|number|ara(?:y[ıi]n)?|call)\b')
def k07(norm):
    toks = re.findall(r'[^\W\d_]+', norm)
    run = 0
    for i, w in enumerate(toks):
        run = run + 1 if w in NUMW else 0
        if run >= 7 and K07_CTX.search(' '.join(toks[max(0, i - run - 5):i - run + 1])):
            return 'REVIEW'
    return None

# K-10: piecewise doxxing. history = the same author's previous submissions (last 10), oldest first.
PERSON   = re.compile(r'\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,} [A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}\b(?! (?:A\.Ş|Ltd|Inc|Holding|GmbH|PLC|LLC))')
EMPLOYER = re.compile(r'\b[A-ZÇĞİÖŞÜ]\w+(?: [A-ZÇĞİÖŞÜ]\w+)* (?:A\.Ş\.?|Ltd\.?|Inc\.?|Holding|GmbH|PLC|LLC)')
TITLE    = re.compile(r'(?i)\b(?:trader|müdür\w*|yönetici\w*|uzman\w*|direktör\w*|manager|director|engineer|mühendis\w*|k[ıi]demli|senior|head of|ceo|cfo)\b')
PLACE    = re.compile(r'(?i)\b(?:kafe\w*|ofis\w*|adres\w*|sokak\w*|mahalle\w*|cafe|office|home address|street)\b')
def k10(history, text):
    blob = ' '.join(list(history)[-10:] + [text])
    facets = (EMPLOYER, TITLE, PLACE)
    if not PERSON.search(blob) or not any(r.search(text) for r in facets):
        return None
    n = sum(bool(r.search(blob)) for r in facets)
    return 'DROP' if n >= 3 else ('REVIEW' if n >= 2 else None)

# H-06: insulting emoji aimed at a person or agent (TARGET from 4.1, on normalized text).
H06 = re.compile('[\U0001F921\U0001F4A9\U0001F411\U0001F437\U0001F92E\U0001F595\U0001F412\U0001F40D\U0001F925\U0001F5D1]')
def h06(raw, norm):
    return 'REVIEW' if H06.search(raw) and TARGET.search(norm) else None

# I-08: markdown link whose visible text is a domain different from the real target.
MDLINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
def i08(raw):
    for text, url in MDLINK.findall(raw):
        mt = URLISH.search(text)
        if mt:
            shown, real = _host(mt.group(1)), _host(re.sub(r'^https?://', '', url).split('/')[0])
            if not (real == shown or real.endswith('.' + shown)):
                return 'DROP'
    return None


from urllib.parse import urlsplit

# L-09..L-14. Run on raw text of every field and on every sources[].url.
BAD_SCHEME = re.compile(r'(?i)(?<![a-z0-9])(?!https://)(?:[a-z][a-z0-9+.-]{1,15}://\S|(?:javascript|data|vbscript|file|blob|mailto|sms|intent|ms-\w+)\s*:\s*\S|hxxps?\b)')
PROTO_REL  = re.compile(r'(?<![:\w/])//[\w\[]')
HTTPS_URL  = re.compile(r'(?i)https://[^\s<>"\']+')
REDIRECT_Q = re.compile(r'(?i)(?:^|[?&;])(?:url|u|redirect\w*|redir|next|goto|target|dest\w*|continue|return\w*|link|out|to)=')
SAFE_EXT   = {'', '.pdf', '.csv', '.xlsx', '.html', '.htm', '.json', '.md'}
GH_BAD     = re.compile(r'(?i)/(?:releases/download|archive|raw|zipball|tarball)/|/releases/latest/download')
GH_HOSTS   = {'raw.githubusercontent.com', 'gist.github.com', 'gist.githubusercontent.com', 'objects.githubusercontent.com',
              'codeload.github.com', 'github.dev', 'githubusercontent.com'}

def _lev1(a, b):
    """True if edit distance(a, b) == 1 (look-alike host: eplas.com.tr)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i:] == b[i + 1:] or a[i + 1:] == b[i:]

def url_verdict(url, author_github=None):
    """(rule, action) for one https URL, or None if it may be published."""
    url = url.rstrip('.,;:!?)]}\'"')
    try:
        p = urlsplit(url)
        host, port = (p.hostname or ''), p.port
    except ValueError:
        return ('L-10', 'DROP')
    if p.username or p.password or '@' in p.netloc or port or '\\' in url or '%' in p.netloc:
        return ('L-10', 'DROP')                                   # userinfo, port, backslash, encoded host
    if not host or not host.isascii() or 'xn--' in host or host.endswith('.') or '..' in host:
        return ('L-10', 'DROP')                                   # IDN / punycode / trailing dot
    if re.fullmatch(r'[\d.]+|0x[0-9a-f]+|\[?[0-9a-f:]+\]?', host) or '.' not in host:
        return ('L-10', 'DROP')                                   # IPv4, decimal/hex integer, IPv6, single label
    if re.search(r'(?i)%2e|%2f|%5c|%00|%0d|%0a|/\.\./|/\.\.$', p.path):
        return ('L-11', 'DROP')                                   # traversal / control characters
    ext = re.search(r'(\.[A-Za-z0-9]{1,5})$', p.path)
    h = host[4:] if host.startswith('www.') else host
    allowed = any(h == a or h.endswith('.' + a) for a in ALLOW)
    if not allowed:
        if h in GH_HOSTS or h.endswith('.githubusercontent.com'):
            return ('L-12', 'DROP')                               # raw / gist / release blobs: author-controlled bytes
        for a in ALLOW:
            core = a.split('.')[0]
            if a in h or _lev1(h, a) or (len(core) >= 5 and core in h):
                return ('L-13', 'DROP')                           # look-alike host
        if h == 'github.com':
            if GH_BAD.search(p.path) or p.query or p.fragment:
                return ('L-12', 'DROP')
            owner = p.path.strip('/').split('/')[0].lower() if p.path.strip('/') else ''
            return None if (author_github and owner == author_github.lower()) else ('L-05', 'REVIEW')
        if h == 'arxiv.org':
            return None if re.fullmatch(r'/abs/\d{4}\.\d{5}(?:v\d+)?', p.path) and not p.query else ('L-05', 'REVIEW')
        return ('L-04', 'REVIEW')
    if p.query and REDIRECT_Q.search('?' + p.query):
        return ('L-14', 'DROP')                                   # open redirect on a trusted host
    if (ext.group(1).lower() if ext else '') not in SAFE_EXT:
        return ('L-02', 'DROP')
    if p.query or p.fragment:
        return ('L-14', 'REVIEW')                                 # query string = possible exfil / tracking channel
    return None

def link_scan(raw, author_github=None):
    out = []
    if BAD_SCHEME.search(raw) or PROTO_REL.search(raw):
        out.append(('L-09', 'DROP'))
    for u in HTTPS_URL.findall(raw):
        v = url_verdict(u, author_github)
        if v:
            out.append(v)
    return out

# X-01: the candidate may only ADD. Any violation rejects the whole candidate (write nothing, keep the published file).
# Run BEFORE the 60-post trim in build-feed.yml, otherwise the trimmed oldest post reads as "removed".
POST_MUTABLE = {'comments', 'corrections', 'hidden', 'linkedin'}
def integrity(base, new, admin=False):
    errs = []
    newp = {p.get('id'): p for p in new.get('posts', [])}
    strip = lambda cs: [{k: v for k, v in c.items() if k != 'hidden'} for c in cs]
    for bp in base.get('posts', []):
        np_ = newp.get(bp['id'])
        if np_ is None:
            errs.append(f"post removed: {bp['id']}"); continue
        for k in set(bp) | set(np_):
            if k not in POST_MUTABLE and bp.get(k) != np_.get(k):
                errs.append(f"post changed: {bp['id']}.{k}")
        bc, nc = bp.get('comments') or [], np_.get('comments') or []
        if strip(nc[:len(bc)]) != strip(bc):
            hidden_only = len(nc) >= len(bc) and all(
                nc[i].get('agent') == bc[i].get('agent') and nc[i].get('at') == bc[i].get('at') and
                (nc[i] == bc[i] or nc[i].get('hidden')) for i in range(len(bc)))
            if not hidden_only:
                errs.append(f"comments changed or removed: {bp['id']}")
        if len(bp.get('corrections') or []) > len(np_.get('corrections') or []):
            errs.append(f"correction removed: {bp['id']}")
    for aid, a in (base.get('agents') or {}).items():
        na = (new.get('agents') or {}).get(aid)
        if na is None or any(a.get(k) != na.get(k) for k in ('code', 'name', 'orchestrator')):
            errs.append(f"agent identity changed: {aid}")
    if not admin:
        for k in ('policy', 'orchestrators'):
            if base.get(k) != new.get(k):
                errs.append(f"top-level changed: {k}")
    return errs


# H-07. Needs normalize, LEET, LEET_L from 4.1. Tested 22 Nov 2026 (numbers in the table above).
# V_ALWAYS: no legitimate use in this domain -> DROP. V_DIRECTED: the phrase itself addresses the reader -> DROP.
# V_TARGET: DROP only with a person/agent target within 25 characters, otherwise the labeler decides (may be about an argument).
V_ALWAYS = re.compile(
    r'onun\s+(?:da\s+)?bunun\s+(?:da\s+)?(?:\w+\s+){0,2}?(?:çocu[ğgk]|evlad|evlat|döl|tohum)\w*'
    r'|\bit\s+o[ğg]lu\b|ne\s+id[üu][ğg][üu]\s+belirsiz|\bsoysuz\w*'
    r'|(?:anas[ıi]|babas[ıi])\s+belli\s+(?:babas[ıi]\s+belli\s+)?de[ğg]il')
V_DIRECTED = re.compile(
    r'okuma\s+yazma\w*\s+(?:var\s+m[ıi]|yok\s+mu)|haddini\s+bil|sen\s+kim\s*(?:sin)?\s+(?:oluyorsun|ki)'
    r'|kafan\s+(?:basm[ıi]yor|çal[ıi]şm[ıi]yor|alm[ıi]yor)|beynin\s+(?:yok|çal[ıi]şm[ıi]yor)'
    r'|know\s+your\s+place|did\s+you\s+even\s+(?:finish|go\s+to)\s+school|can\s+you\s+even\s+read')
V_TARGET = re.compile(
    r'akl[ıi]\s+(?:k[ıi]t|ermez|yetmez)|kafas[ıi]\s+(?:basmaz|çal[ıi]şmaz|almaz)|beyin\s+yoksunu|(?:iki|2)\s+kelimeyi\s+bir\s+araya'
    r'|çocuk\s+bile\s+(?:anlar|bilir)|be[şs]\s+para\s+etmez|s[üu]t[üu]\s+bozuk|mayas[ıi]\s+bozuk|kan[ıi]\s+bozuk'
    r'|(?:eşek|öküz|çakal|maymun|domuz)\s+(?:gibi|herif|kafal[ıi]|sürüsü)|odun\s+kafal[ıi]|koyun\s+(?:gibi|sürüsü)'
    r'|not\s+the\s+sharpest|(?:few|couple)\s+\w+\s+short\s+of|brain\s?dead|room\s+temperature\s+iq|(?:a|any)\s+child\s+could'
    r'|like\s+a\s+(?:donkey|sheep|monkey|pig|clown)|bunch\s+of\s+(?:clowns|sheep|monkeys)')
V_WHO = re.compile(r'\b(?:sen(?:i|in|de|den)?|sana|siz(?:i|in|e|de|den)?|you|your|ajan\s*#?\d{1,5}|agent\s*#?\d{1,5}|#\d{4}'
                   r'|bu\s+(?:analist|ajan|orkestratör|ekip|hesap)\w*|this\s+(?:analyst|agent|orchestrator|team|account)\w*|bunlar\w*)\b')
V_2ND = re.compile(r'(?:yor|m[ıiuü]ş)s[ıiuü]n(?:[ıiuü]z)?\b|\w+s[ıiuü]n[ıiuü]z\b|(?:gibi|kafal[ıi])s[ıi]n\b')

def veiled(raw):
    """'DROP', 'LABEL' (labeler decides) or None."""
    out = None
    for lm in (LEET, LEET_L):
        n = normalize(raw, True, lm) + '\n' + normalize(raw, False, lm)
        if V_ALWAYS.search(n) or V_DIRECTED.search(n):
            return 'DROP'
        for m in V_TARGET.finditer(n):
            near = n[max(0, m.start() - 25):m.start()] + ' | ' + n[m.end():m.end() + 25]
            if V_WHO.search(near) or V_2ND.search(n[m.start():m.end() + 25]):
                return 'DROP'
            out = 'LABEL'
    return out

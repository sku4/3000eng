#!/usr/bin/env python3
"""Generate British RP (non-rhotic) IPA transcriptions from CMUdict.

Used by merge_dicts.py to replace OCR-mangled transcriptions with correct IPA.
CMUdict ships US-rhotic ARPABET; we post-process to non-rhotic RP to match the
book's convention (the book prints non-rhotic transcriptions: start=[sta:t],
turn=[tз:n], warn=[wэ:n] — no post-vocalic R).

Public API: transcribe(en) -> "[...]" IPA string (or "" if unresolvable).
"""
import re
import pronouncing as pr

# --- ARPABET -> IPA ------------------------------------------------------------
# Base vowel IPA (no following R). AO default is LOT /ɒ/; THOUGHT words without
# R are listed in _THOUGHT_NO_R and mapped to /ɔː/.
_VOWEL = {
    'AA': 'ɒ', 'AE': 'æ', 'AH': 'ʌ', 'AO': 'ɒ', 'AW': 'aʊ', 'AY': 'aɪ',
    'EH': 'e', 'ER': 'ɜː', 'EY': 'eɪ', 'IH': 'ɪ', 'IY': 'i', 'OW': 'əʊ',
    'OY': 'ɔɪ', 'UH': 'ʊ', 'UW': 'u',
}
# vowel + following non-prevocalic R -> RP long/centering vowel
_VOWEL_R = {
    'AA': 'ɑː', 'AE': 'eə', 'AH': 'ɜː', 'AO': 'ɔː', 'AW': 'aʊə', 'AY': 'aɪə',
    'EH': 'eə', 'ER': 'ɜː', 'EY': 'eɪə', 'IH': 'ɪə', 'IY': 'ɪə', 'OW': 'əʊ',
    'OY': 'ɔɪə', 'UH': 'ʊə', 'UW': 'ʊə',
}
_CONS = {
    'B': 'b', 'CH': 'tʃ', 'D': 'd', 'DH': 'ð', 'F': 'f', 'G': 'ɡ', 'HH': 'h',
    'JH': 'dʒ', 'K': 'k', 'L': 'l', 'M': 'm', 'N': 'n', 'NG': 'ŋ', 'P': 'p',
    'R': 'r', 'S': 's', 'SH': 'ʃ', 'T': 't', 'TH': 'θ', 'V': 'v', 'W': 'w',
    'Y': 'j', 'Z': 'z', 'ZH': 'ʒ',
}
# Stressed tense vowels get a length mark (the book used [i:], [u:]).
_LONG_WHEN_STRESSED = {'IY': 'iː', 'UW': 'uː'}
# THOUGHT lexical-set words whose ARPABET is AO WITHOUT a following R — these
# keep /ɔː/ in RP; every other AO-without-R word is LOT /ɒ/.
_THOUGHT_NO_R = {
    'all', 'ball', 'bald', 'bawl', 'call', 'crawl', 'draw', 'draws', 'drawing',
    'drawn', 'flaw', 'flaws', 'fall', 'falls', 'fallen', 'false', 'fault',
    'halt', 'hall', 'mall', 'small', 'tall', 'wall', 'walk', 'walks', 'walking',
    'talk', 'talks', 'talking', 'chalk', 'law', 'laws', 'claw', 'raw', 'straw',
    'saw', 'yawn', 'yawns', 'dawn', 'caught', 'bought', 'brought', 'taught',
    'thought', 'thoughts', 'fought', 'ought', 'aught', 'daughter', 'slaughter',
    'assault', 'exhausted', 'broad', 'abroad',
}

# Hand-written ARPABET for words CMUdict lacks (British spellings / absent).
_FALLBACK_ARPA = {
    'analyse': 'AE1 N AH0 L AY2 Z',
    'colourless': 'K AH1 L ER0 L AH0 S',
    'odourless': 'OW1 D ER0 L AH0 S',
    'skilful': 'S K IH1 L F AH0 L',
    'unskilful': 'AH2 N S K IH1 L F AH0 L',
    'dexterous': 'D EH1 K S T R AH0 S',
    'impudent': 'IH1 M P Y AH0 D AH0 N T',
    'incautious': 'IH2 N K AO1 SH AH0 S',
    'seemly': 'S IY1 M L IY0',
    'spoilt': 'S P OY1 L T',
    'unfasten': 'AH2 N F AE1 S AH0 N',
    'unselfish': 'AH2 N S EH1 L F IH0 SH',
    'perm': 'P ER1 M',
    'particoloured': 'P AA2 R T IY0 K AH1 L ER0 D',
    # 3001eng photo set: compounds & British words CMUdict lacks (verified RP
    # ARPABET — the existing non-rhotic post-processing then renders them).
    'waggon': 'W AE1 G AH0 N',
    'aeroplane': 'EH1 R OW0 P L EY1 N',
    'giddiness': 'G IH1 D IY0 N AH0 S',
    'toothache': 'T UW1 TH EY1 K',
    'earache': 'IY1 R EY1 K',
    'cashdesk': 'K AE1 SH D EH1 S K',
    'roadmarking': 'R OW1 D M AA1 R K IH0 NG',
    'windscreen': 'W AY1 N D S K R IY1 N',
    'trolleybus': 'T R AA1 L IY0 B AH1 S',
    'airhostess': 'EH1 R HH OW1 S T AH0 S',
    'motorway': 'M OW1 T ER0 W EY1',
    'furcoat': 'F ER1 K OW1 T',
    'underclothes': 'AH1 N D ER0 K L OW1 DH Z',
    'bedclothes': 'B EH1 D K L OW1 DH Z',
    'pillowcase': 'P IH1 L OW0 K EY1 S',
    'greengrocery': 'G R IY1 N G R OW1 S ER0 IY0',
    'forenoon': 'F AO1 R N UW1 N',
    'overestimation': 'OW1 V ER0 EH2 S T AH0 M EY1 SH AH0 N',
    'underestimation': 'AH1 N D ER0 EH2 S T AH0 M EY1 SH AH0 N',
    'longjump': 'L AO1 NG JH AH1 M P',
    'coalmine': 'K OW1 L M AY1 N',
    'crucian': 'K R UW1 SH AH0 N',
    'gosling': 'G AA1 Z L IH0 NG',
    'besom': 'B IY1 Z AH0 M',
    'currant': 'K AH1 R AH0 N T',
    'quadrangle': 'K W AA1 D R AE2 NG G AH0 L',
    'diffidence': 'D IH1 F IH0 D AH0 N S',
    'urbanity': 'ER0 B AE1 N IH0 T IY0',
    'tactlessness': 'T AE1 K T L AH0 S N AH0 S',
    'impertinence': 'IH2 M P ER1 T AH0 N AH0 N S',
    'impudence': 'IH1 M P Y AH0 D AH0 N S',
    'offence': 'AH0 F EH1 N S',
    'rancour': 'R AE1 NG K ER0',
    'pyjamas': 'P AH0 JH AA1 M AH0 Z',
    'plimsolls': 'P L IH1 M S AH0 L Z',
    'cravat': 'K R AH0 V AE1 T',
    'groats': 'G R OW1 T S',
    'rhombus': 'R AA1 M B AH0 S',
    'repertoire': 'R EH1 P ER0 T W AA1 R',
    'preposition': 'P R IY2 P AH0 Z IH1 SH AH0 N',
    'precipitations': 'P R IH0 S IH2 P IH0 T EY1 SH AH0 N Z',
    'hoarfrost': 'HH AO1 R F R AO2 S T',
    'snowdrop': 'S N OW1 D R AO2 P',
    'earlobe': 'IY1 R L OW0 B',
    'ardour': 'AA1 R D ER0',
}

def _arpabet(word):
    """Return ARPABET phone list for a single lowercase word, or []."""
    if word in _FALLBACK_ARPA:
        return _FALLBACK_ARPA[word].split()
    phones = pr.phones_for_word(word)
    return phones[0].split() if phones else []

def _vowel_ipa(base, stress, word):
    if base == 'AH':
        return 'ə' if stress in (0, None) else 'ʌ'
    if base == 'ER':
        return 'ə' if stress in (0, None) else 'ɜː'
    if base == 'AO':
        # THOUGHT words (all, law, small, walk, …) keep /ɔː/; every other
        # AO-without-R word is LOT /ɒ/ in RP (cross, belong, off, long, …).
        return 'ɔː' if word in _THOUGHT_NO_R else 'ɒ'
    if stress in (1, 2) and base in _LONG_WHEN_STRESSED:
        return _LONG_WHEN_STRESSED[base]
    return _VOWEL[base]

def _vowel_r_ipa(base, stress):
    # merged with a following non-prevocalic R
    if base in ('AH', 'ER'):
        return 'ɜː' if stress in (1, 2) else 'ə'
    return _VOWEL_R.get(base, _VOWEL.get(base, ''))

def _phones_to_ipa(tokens, word=''):
    segs = []
    for tok in tokens:
        m = re.match(r'([A-Z]+)([012]?)', tok)
        if not m:
            continue
        base = m.group(1)
        stress = int(m.group(2)) if m.group(2) else None
        segs.append({'base': base, 'stress': stress})
    n = len(segs)
    res = []  # {'ipa','vowel','stress','base'}
    for i, s in enumerate(segs):
        base, stress = s['base'], s['stress']
        if base == 'R':
            nxt_vowel = i + 1 < n and segs[i + 1]['base'] in _VOWEL
            if nxt_vowel:
                res.append({'ipa': 'r', 'vowel': False, 'stress': None})
            else:
                if res and res[-1]['vowel']:
                    v = res.pop()
                    long = _vowel_r_ipa(v.get('base'), v.get('stress'))
                    res.append({'ipa': long, 'vowel': True, 'stress': v.get('stress')})
                # else: stray R with no vowel -> drop
            continue
        if base in _VOWEL:
            res.append({'ipa': _vowel_ipa(base, stress, word),
                        'vowel': True, 'stress': stress, 'base': base})
            # ER bundles its own R (no separate R token in ARPABET); before a
            # vowel that R links, so emit a linking r (interrupt -> /ˌɪntəˈrʌpt/).
            nxt_vowel = i + 1 < n and segs[i + 1]['base'] in _VOWEL
            if base == 'ER' and nxt_vowel:
                res.append({'ipa': 'r', 'vowel': False, 'stress': None})
        else:
            c = _CONS.get(base)
            if c:
                res.append({'ipa': c, 'vowel': False, 'stress': None})
    # assemble with stress mark before each stressed syllable's onset
    out = []
    onset_start = 0
    after_vowel = True
    for r in res:
        if r['vowel']:
            if r['stress'] == 1:
                out.insert(onset_start, 'ˈ')
            elif r['stress'] == 2:
                out.insert(onset_start, 'ˌ')
            out.append(r['ipa'])
            after_vowel = True
        else:
            if after_vowel:
                onset_start = len(out)
                after_vowel = False
            out.append(r['ipa'])
    return ''.join(out)

def _transcribe_word(word):
    w = word.lower().strip(" ;:,.\"'`()-")
    if not w:
        return ''
    toks = _arpabet(w)
    if not toks:
        # possessive 's: hairdresser's, one's, children's -> base + /ɪz|z/
        if w.endswith("'s") and len(w) > 3:
            base = _transcribe_word(w[:-2])
            if base:
                return base + ('ɪz' if base.endswith(('s', 'ʃ', 'tʃ', 'z', 'ʒ', 'θ')) else 'z')
        # try splitting a hyphenated compound (absent-minded -> absent + minded)
        if '-' in w:
            parts = [_transcribe_word(p) for p in w.split('-')]
            if all(parts):
                return ''.join(parts)
        return ''
    return _phones_to_ipa(toks, w)

def transcribe(en):
    """Return "[ipa]" for an English phrase, or "" if it cannot be resolved.
    Parenthesized words — (into), (along), (left) — are transcribed and kept in
    parens. Grammatical markers — (+adj), (+прил.) — are dropped (not spoken)."""
    if not en:
        return ''
    s = re.sub(r'\(\+adj[\.)]*\)', '', en)
    s = re.sub(r'\(\+прил[\.)]*\)', '', s)
    pieces = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == '(':
            j = s.find(')', i)
            inner = s[i + 1:j] if j != -1 else s[i + 1:]
            ipa = _transcribe_word(inner)
            if ipa:
                pieces.append('(' + ipa + ')')
            i = (j + 1) if j != -1 else n
        elif ch.isalpha() or ch in "'-":
            j = i
            while j < n and (s[j].isalpha() or s[j] in "'-"):
                j += 1
            ipa = _transcribe_word(s[i:j])
            if ipa:
                pieces.append(ipa)
            i = j
        else:
            i += 1
    ipa = ' '.join(pieces)
    return '[' + ipa + ']' if ipa else ''

if __name__ == '__main__':
    import sys
    for w in sys.argv[1:]:
        print(w, '->', transcribe(w))

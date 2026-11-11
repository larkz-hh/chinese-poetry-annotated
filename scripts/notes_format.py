"""Conservative plain-note formatting with exact source-quotation accounting."""
import hashlib
import json
import re

NOTES_FORMAT = 'plain-notes-v1'
PINYIN = re.compile(r'([\u3400-\u9fff])[（(]([A-Za-züÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜêɑɡńňǹḿ0-9 ·\-]+)[）)]')
NUMBER = re.compile(r'^\s*(?:(?:[①-⑳⑴-⒇❶-❿]|\[\d{1,3}\]|[（(]\d{1,3}[）)]|\d{1,3}(?:\.(?!\d)|、))\s*)+')
CHINESE = re.compile(r'[\u3400-\u9fff]')


def notes_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def reference_form(text):
    text = PINYIN.sub(r'\1', text)
    text = re.sub(r'[（(]\s*[）)]', '', text).replace('?', '？').replace('!', '！')
    return ''.join(c for c in text if not c.isspace() and c not in '“”「」『』')


def reference_map(text):
    ignored = set()
    for match in PINYIN.finditer(text):
        ignored.update(range(match.start()+1, match.end()))
    for match in re.finditer(r'[（(]\s*[）)]', text):
        ignored.update(range(match.start(), match.end()))
    chars, positions = [], []
    for i,char in enumerate(text):
        if i not in ignored and not char.isspace() and char not in '“”「」『』':
            chars.append({'?':'？','!':'！'}.get(char,char))
            positions.append(i)
    return ''.join(chars), positions


def strip_body_prefix(text, content):
    """Only remove complete leading clauses actually found verbatim in the body."""
    body = reference_form(''.join(content))
    rest = text.strip()
    removed = []
    readings = []
    while rest:
        # Source prose may itself contain colons and quoted speech. Match the
        # complete sentence before interpreting any colon as a definition.
        plain, positions = reference_map(rest)
        units = [reference_form(s) for s in content if len(CHINESE.findall(reference_form(s))) >= 8]
        whole = [positions[len(unit)-1]+1 for unit in units if plain.startswith(unit)]
        complete = [positions[i]+1 for i,c in enumerate(plain)
                    if c in '。！？' and len(CHINESE.findall(plain[:i+1])) >= 8
                    and plain[:i+1] in body]
        if whole or complete:
            cut = max(whole+complete)
            quote, rest = rest[:cut], rest[cut:]
            while rest.startswith(('”','」','』')):
                quote, rest = quote+rest[0], rest[1:]
            removed.append(quote)
            readings.extend((m.group(1),m.group(2)) for m in PINYIN.finditer(quote))
            rest = rest.strip()
            continue
        colons=top_level_colons(rest)
        if colons:
            end=colons[0]
            label=reference_form(rest[:end]).strip('。！？!?；;，,')
            quoted_label=(any(c in rest[:end] for c in '，,。！？!?；;') or len(CHINESE.findall(label))>=12)
            if label and quoted_label and label in body and len(CHINESE.findall(label))>=4:
                quote=rest[:end+1]
                removed.append(quote)
                readings.extend((m.group(1),m.group(2)) for m in PINYIN.finditer(quote))
                tail=rest[end+1:].strip()
                markers=term_markers(tail)
                rest=tail if markers and markers[0][0]==0 else '句意说明：'+tail
                break
        plain, positions = reference_map(rest)
        cut = 0
        for i,char in enumerate(plain):
            if char in '：:':
                break
            if char in '，,。！？!?；;' and len(CHINESE.findall(plain[:i+1])) >= 4:
                prefix = plain[:i+1]
                if char in '，,' and prefix not in {reference_form(s) for s in content}:
                    continue
                if prefix in body:
                    cut = positions[i]+1
        if not cut:
            # Fragments without a terminal mark can still be pure placeholders.
            if len(CHINESE.findall(plain)) >= 4 and plain in body:
                cut = len(rest)
            else:
                break
        quote = rest[:cut]
        tail = rest[cut:]
        while tail.startswith(('”','」','』')):
            quote += tail[0]
            tail = tail[1:]
        removed.append(quote)
        readings.extend((m.group(1),m.group(2)) for m in PINYIN.finditer(quote))
        rest = tail.strip()
    return rest, removed, readings


def top_level_positions(text, delimiters):
    pairs={'（':'）','(':')','“':'”','「':'」','『':'』','《':'》','【':'】','[':']'}
    stack=[]
    result=[]
    for i,char in enumerate(text):
        if char in pairs:
            stack.append(pairs[char])
        elif stack and char==stack[-1]:
            stack.pop()
        elif char in delimiters and not stack:
            result.append(i)
    return result


def top_level_colons(text):
    return top_level_positions(text,'：:')


def term_markers(text):
    """A new lemma needs a sentence/separator boundary and a bounded term name."""
    markers=[]
    for colon in top_level_colons(text):
        start=colon
        while start>0 and text[start-1].isspace():
            start-=1
        depth=0
        while start>0:
            char=text[start-1]
            if char in '）)':
                depth+=1
            elif char in '（(' and depth:
                depth-=1
            if depth==0 and (char in '。！？!?；;\n\r' or char.isspace()):
                break
            start-=1
        lemma=text[start:colon].strip()
        while start<colon and text[start] in '”」』':
            start+=1
        lemma=text[start:colon].strip()
        stripped=NUMBER.sub('',lemma).strip('“”「」『』')
        plain=PINYIN.sub(r'\1',stripped)
        if (not plain or len(plain)>24 or any(c in plain for c in '，,。！？!?；;：:《》')
                or not CHINESE.search(plain)):
            continue
        if markers and len(plain)>1 and plain.endswith(('曰','说','云','记载','指出')):
            continue
        markers.append((start,colon))
    return markers


def split_terms(text):
    text=NUMBER.sub('',text).strip()
    if not text:
        return []
    if text.startswith(('异文：','版本说明：')):
        return [text]
    markers=term_markers(text)
    if not markers:
        return [text]
    starts=[start for start,_ in markers]
    # Keep introductory explanations attached to their first meaningful term.
    if starts[0]>0:
        starts[0]=0
    output=[]
    for start,end in zip(starts,starts[1:]+[len(text)]):
        item=NUMBER.sub('',text[start:end]).strip()
        colons=top_level_colons(item)
        if colons:
            position=colons[0]
            item=item[:position].rstrip()+'：'+item[position+1:].lstrip()
        if item.endswith(('；',';')):
            item=item[:-1]+'。'
        if item:
            output.append(item)
    return output


def detach_leading_variants(text):
    """Keep source variant labels as independent notes, including nested pinyin."""
    variants=[]
    while text.startswith(('(', '（')):
        stack=[]
        end=None
        pairs={'(':')','（':'）'}
        for i,char in enumerate(text):
            if char in pairs:
                stack.append(pairs[char])
            elif stack and char in ')）':
                stack.pop()
                if not stack:
                    end=i
                    break
        if end is None:
            break
        value=text[1:end].strip()
        if not re.search(r'一作|又作|通[:：]|同[:：]|版本[一二三四五六七八九十\d]',value):
            break
        label='版本说明' if value.startswith('版本') else '异文'
        variants.append(label+'：'+value.replace(':','：').rstrip('。')+'。')
        text=text[end+1:].strip()
    return variants,text


def standardize_comma_definitions(text, content):
    """Turn an explicit body-term/comma definition into the same colon layout."""
    body=reference_form(''.join(content))
    # Sentence and semicolon boundaries only; explanation commas remain untouched.
    stops=[i+1 for i in top_level_positions(text,'。！？!?；;')]
    parts=[text[a:b] for a,b in zip([0]+stops,stops+[len(text)]) if b>a]
    output=[]
    for part in parts:
        head=len(part)-len(part.lstrip())
        current=part[head:]
        comma=re.search('[，,]',current)
        if comma and not any(c in current[:comma.start()] for c in '：:'):
            lemma=current[:comma.start()].strip()
            plain=reference_form(lemma)
            phonetic=re.fullmatch(r'([\u3400-\u9fff]+)音([A-Za-züÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜêɑɡńňǹḿ]+)',lemma)
            if phonetic:
                plain=phonetic.group(1)
                lemma=plain+'（'+phonetic.group(2)+'）'
            if plain and len(plain)<=12 and all(CHINESE.fullmatch(c) for c in plain) and plain in body:
                part=part[:head]+lemma+'：'+current[comma.end():]
        output.append(part)
    return ''.join(output)


def normalize_notes(poem):
    output=[]
    operations=[]
    readings=[]
    for index,text in enumerate(poem['notes']):
        clean=NUMBER.sub('',text).strip()
        clean,removed,pronunciations=strip_body_prefix(clean,poem['content'])
        readings.extend(pronunciations)
        variants,clean=detach_leading_variants(clean)
        clean=standardize_comma_definitions(clean,poem['content'])
        entries=variants+split_terms(clean)
        output.extend(entries)
        if removed or entries!=[text]:
            operations.append(dict(index=index,removed_body_quotes=removed,entries=entries))
    unattached=[]
    for char,pronunciation in dict.fromkeys(readings):
        placed=False
        for i,item in enumerate(output):
            markers=term_markers(item)
            if not markers or markers[0][0]!=0:
                continue
            colon=markers[0][1]
            lemma=item[:colon]
            if char not in lemma:
                continue
            existing=[m.group(2) for m in PINYIN.finditer(lemma) if m.group(1)==char]
            if existing and pronunciation not in existing:
                continue
            if not existing:
                position=lemma.index(char)+1
                lemma=lemma[:position]+'（'+pronunciation+'）'+lemma[position:]
                output[i]=lemma+item[colon:]
            placed=True
            break
        if not placed and not any(char in s and pronunciation in s for s in output):
            unattached.append(f'{char}（{pronunciation}）：读音。')
    output.extend(unattached)
    return output,operations


def apply_notes_normalization(poem, records):
    entry=records.get(poem['id'])
    if entry is None:
        return None
    if (not isinstance(entry.get('before'),list) or not isinstance(entry.get('after'),list)
            or not entry['after'] or any(not isinstance(s,str) or not s.strip() for s in entry['after'])
            or entry.get('semantic_change') and not entry.get('evidence')):
        raise ValueError(f'Invalid note normalization: {poem["id"]}')
    if (entry.get('body_hash')!=poem['body_hash']
            or poem['notes'] not in (entry.get('before'),entry.get('after'))
            or notes_hash(entry['before'])!=entry.get('before_hash')
            or notes_hash(entry['after'])!=entry.get('after_hash')):
        raise ValueError(f'Stale note normalization: {poem["id"]}')
    poem['notes']=list(entry['after'])
    if not poem['notes']:
        raise ValueError(f'Note normalization needs a real annotation: {poem["id"]}')
    return dict(version=NOTES_FORMAT,changed=entry['before']!=entry['after'],
        before_hash=entry['before_hash'],after_hash=entry['after_hash'],
        source_record='raw/notes_normalization.json',semantic_change=bool(entry.get('semantic_change')))

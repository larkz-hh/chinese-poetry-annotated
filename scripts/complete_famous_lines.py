"""Select representative card excerpts for every work; resumable, exact-text only."""
import argparse
import concurrent.futures
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.error

from complete_annotations import configuration, request_json, CreditUnavailable
from data_utils import ROOT, load, dump
from famous_lines import attach_famous_lines, validate_famous_lines

PROMPT_VERSION = 'representative-lines-v1'


def candidates(poem):
    edition = next(e for e in poem['editions'] if e['is_primary'])
    units = edition['units']
    body = ''.join(u['text'] for u in units)
    boundaries, offset = [], 0
    spans = []
    for unit in units:
        boundaries.append((offset, offset + len(unit['text']), unit['id']))
        spans.append((offset, offset + len(unit['text'])))
        offset += len(unit['text'])
    # Complete sentences and two/three-clause windows also cover long prose units.
    sentences = list(re.finditer(r'[^。！？!?；;]+[。！？!?；;]?', body))
    spans.extend((m.start(), m.end()) for m in sentences)
    clauses = list(re.finditer(r'[^，,。！？!?；;]+[，,。！？!?；;]?', body))
    for i in range(len(clauses)):
        for size in (1, 2, 3):
            if i + size <= len(clauses):
                last = clauses[i+size-1]
                if body[last.end()-1] not in '，,':
                    spans.append((clauses[i].start(), last.end()))
    result, seen = [], set()
    for start, end in sorted(set(spans)):
        text = body[start:end].strip()
        if not text or text in seen or len(text) > 100:
            continue
        if len(re.findall(r'[\u3400-\u9fff]', text)) < min(6, len(re.findall(r'[\u3400-\u9fff]', body))):
            continue
        if text.startswith(('(', '（')) or text.endswith(('，', ',')):
            continue
        start += len(body[start:end]) - len(body[start:end].lstrip())
        end = start + len(text)
        ids = [uid for a, b, uid in boundaries if a < end and b > start]
        quote = dict(id=poem['id']+':q1', text=text, unit_ids=ids, source_url=poem['source'])
        trial = dict(poem, famous_lines=[quote])
        try:
            validate_famous_lines([trial])
        except ValueError:
            continue
        seen.add(text)
        result.append(dict(text=text, unit_ids=ids, start=start, end=end))
    if not result:
        raise ValueError(f'No exact bounded card candidate: {poem["id"]}')
    return result


def candidate_digest(poem, choices):
    payload = dict(body_hash=poem['body_hash'], candidates=choices, prompt_version=PROMPT_VERSION)
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_choices(poem, options, selected):
    if (not isinstance(selected, list) or not 1 <= len(selected) <= 3
            or any(type(i) is not int or not 0 <= i < len(options) for i in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('Expected 1 to 3 distinct candidate indexes')
    ordered = sorted((options[i]['start'],options[i]['end']) for i in selected)
    if any(a[1] > b[0] for a,b in zip(ordered,ordered[1:])):
        raise ValueError('Selected excerpts overlap')
    quotes = [dict(id=f'{poem["id"]}:q{n+1}', text=options[i]['text'],
        unit_ids=options[i]['unit_ids'],source_url=poem['source']) for n,i in enumerate(selected)]
    body=''.join(poem['content'])
    if len(body)>=30 and len(options)>1 and any(q['text']==body for q in quotes):
        raise ValueError('Choose an excerpt rather than the full work')
    validate_famous_lines([dict(poem,famous_lines=quotes)])
    return quotes


def select_batch(batch, config):
    items = [dict(id=p['id'],title=p['title'],author=p['author'],genre=p['genre'],
        candidates=[dict(index=i,text=c['text']) for i,c in enumerate(options)
            if not (len(''.join(p['content']))>=30 and len(options)>1 and c['text']==''.join(p['content']))]) for p,options in batch]
    prompt = ('为古诗词阅读App选择每篇作品适合单独展示的代表句，必须逐篇返回，不允许漏项。'
        '从候选中优先选取广为传诵的名句；没有确定名句时，选择最能表现作品情绪、意象、主题或哲理的代表句。'
        '每篇选1至3个候选，多选仅用于确有不同代表句的作品，所选片段不得互相重叠。'
        '保留完整表达，不选序言、题解、版本说明或仅有承接作用的零碎句，不能把全篇多首合集当一个名句。'
        '只输出候选编号，不重新抄写或改写原文。不声称已完成外部文献核查。'
        '每篇补一条简短中文选句理由，重点说明所选内容体现了什么，不空泛重复“著名”“经典”。'
        '格式严格为 {"selections":[{"id":"作品ID","candidate_ids":[编号],"reason":"选句理由"}]}。\n'
        +json.dumps(items,ensure_ascii=False,separators=(',',':')))
    last_error = None
    for attempt in range(3):
        try:
            attempt_prompt=prompt
            if attempt:
                attempt_prompt+='\n上一轮未通过结构或片段重叠校验。本轮每篇只选最有代表性的1个候选编号，仍须覆盖全部作品。'
            value,usage=request_json(config,'你是古诗文阅读编辑。只从给定原文候选选择代表句，输出合法JSON。',attempt_prompt,budget=4096)
            rows=value.get('selections')
            if not isinstance(rows,list) or len(rows)!=len(batch):
                raise ValueError('Missing batch selections')
            by_id={r.get('id'):r for r in rows if isinstance(r,dict)}
            if set(by_id)!={p['id'] for p,_ in batch}:
                raise ValueError('Invalid or duplicate selected work IDs')
            output=[]
            for poem,options in batch:
                row=by_id[poem['id']]
                reason=row.get('reason')
                if not isinstance(reason,str) or not reason.strip():
                    raise ValueError('Missing selection reason')
                quotes=validate_choices(poem,options,row.get('candidate_ids'))
                output.append(dict(id=poem['id'],body_hash=poem['body_hash'],
                    candidate_hash=candidate_digest(poem,options),famous_lines=quotes,
                    selection_type='ai_selected',reason=reason,model=config['LLM_MODEL_ID'],
                    prompt_version=PROMPT_VERSION,selected_at=datetime.now(timezone.utc).isoformat(),
                    batch_usage=usage if not output else None))
            return output
        except CreditUnavailable:
            raise
        except urllib.error.HTTPError as exc:
            last_error=f'HTTP {exc.code}'
            if exc.code in (401,403):
                break
        except urllib.error.URLError:
            raise RuntimeError('network_unavailable') from None
        except (ValueError,KeyError,TypeError) as exc:
            last_error=type(exc).__name__+': '+str(exc)[:120]
    raise RuntimeError(last_error or 'selection_failed')


def compile_catalog(poems, current, selected):
    output=copy.deepcopy(current)
    for poem in poems:
        pid=poem['id']
        if pid in output['works'] and output['works'][pid]['famous_lines']:
            continue
        record=selected.get(pid)
        if not record or record['body_hash']!=poem['body_hash']:
            raise ValueError(f'Missing or stale selection: {pid}')
        validate_famous_lines([dict(poem,famous_lines=record['famous_lines'])])
        output['works'][pid]=dict(body_hash=poem['body_hash'],famous_lines=record['famous_lines'],
            selection=dict(type=record['selection_type'],reason=record['reason'],model=record['model'],
                prompt_version=record['prompt_version'],selected_at=record['selected_at']))
    output.update(coverage='complete',require_all_works=True,expected_works=len(poems),
        selection_type='source_selections_and_ai_selected_representative_excerpts',
        note='每篇至少一组卡片代表句；保留原有来源选句，新选句经AI选择及原文精确校验，不将全部代表句宣称为公认名句。')
    attach_famous_lines(copy.deepcopy(poems),output)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--input-poems',type=Path,default=ROOT/'app-data/poems.json',
        help='Canonical JSON for the complete target collection, including any new works')
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--batch-size',type=int,default=8)
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--compile',action='store_true')
    args=parser.parse_args()
    if args.workers<1 or args.batch_size<1 or args.limit<0:
        parser.error('workers/batch-size must be positive; limit must be nonnegative')
    poems=load(args.input_poems)
    catalog=load(ROOT/'raw/famous_lines.json')
    path=ROOT/'raw/famous_line_selections.jsonl'
    selected={}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if 'error' not in row:
                selected[row['id']]=row
    todo=[]
    for poem in poems:
        if catalog['works'].get(poem['id'],{}).get('famous_lines'):
            continue
        options=candidates(poem)
        old=selected.get(poem['id'])
        if old and old.get('candidate_hash')==candidate_digest(poem,options):
            lookup={(o['text'],tuple(o['unit_ids'])):i for i,o in enumerate(options)}
            try:
                indexes=[lookup[(q['text'],tuple(q['unit_ids']))] for q in old['famous_lines']]
                validate_choices(poem,options,indexes)
                validate_famous_lines([dict(poem,famous_lines=old['famous_lines'])])
                continue
            except (KeyError,ValueError):
                pass
        todo.append((poem,options))
    if args.limit:
        todo=todo[:args.limit]
    print(json.dumps(dict(pending=len(todo),resumed=len(selected),workers=args.workers),ensure_ascii=False),flush=True)
    failures=0
    if todo:
        config=configuration(args.env_file)
        batches=[todo[i:i+args.batch_size] for i in range(0,len(todo),args.batch_size)]
        with path.open('a',encoding='utf-8',newline='\n') as stream, concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(select_batch,batch,config):batch for batch in batches}
            completed=0
            for future in concurrent.futures.as_completed(futures):
                batch=futures[future]
                try:
                    records=future.result()
                except Exception as exc:
                    failures+=len(batch)
                    records=[dict(id=p['id'],body_hash=p['body_hash'],error=type(exc).__name__+': '+str(exc)[:140]) for p,_ in batch]
                    if isinstance(exc,CreditUnavailable):
                        for task in futures:
                            task.cancel()
                for row in records:
                    stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                    if 'error' not in row:
                        selected[row['id']]=row
                stream.flush()
                completed+=len(batch)
                print(json.dumps(dict(completed=completed,total=len(todo),failures=failures),ensure_ascii=False),flush=True)
    if failures:
        raise SystemExit(f'{failures} works need retry; successful selections were retained')
    if args.compile:
        result=compile_catalog(poems,catalog,selected)
        dump(ROOT/'raw/famous_lines.json',result,newline='\n')
        print(json.dumps(dict(compiled_works=len(result['works']),quotes=sum(len(e['famous_lines']) for e in result['works'].values())),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()

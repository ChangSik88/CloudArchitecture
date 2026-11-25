"""AI Hub 민원(콜센터) 쇼핑 데이터에서 식품관, 패션관 상담 사례를 뽑는다.

- 대상 카테고리: 배송, 교환, 반품, AS (주문, 결제, 업무처리는 제외)
- 지식베이스의 'OOO/상품' 값으로 상품을 찾고, 키워드로 식품/패션을 나눈다.
  둘 다 걸리거나 어느 쪽도 아니면 버린다.
- 고객 의도에 배송 문의, 교환, 반품, 불량 같은 주문 이후 문제가 없는 대화(방송 중 주문 통화)는 버린다.
- 본인 확인(이름, 전화번호, 주소) 턴은 빼고 대화 흐름만 남긴다.

결과는 AI Hub 라이선스상 제3자 제공이 금지되므로 저장소에 올리지 않는다 (data/ 는 .gitignore).

사용법:
    python scripts/prepare_cases.py "<...>/022.민원(콜센터) 질의-응답 데이터/01.데이터"
"""

import collections
import json
import sys
import zipfile
from pathlib import Path

CATEGORIES = ["배송", "교환", "반품", "AS"]
SPLITS = {"1.Training": "train", "2.Validation": "valid"}
OUT = Path(__file__).resolve().parent.parent / "data" / "aihub"

FOOD = ["갈비", "갈치", "전복", "김치", "장조림", "스테이크", "불고기", "떡", "새우", "포도", "즙",
        "고기", "한우", "굴비", "생선", "오징어", "고등어", "만두", "젓갈", "햄", "소시지", "닭",
        "삼겹", "사과", "귤", "한라봉", "견과", "쌀", "홍삼", "과자", "꽃게", "게장", "낙지", "주꾸미",
        "랍스터", "연어", "장어", "곰탕", "육포", "한과", "과일", "망고", "수박", "멜론", "딸기",
        "식품", "반찬", "족발", "보쌈", "떡갈비", "돈까스", "돈가스", "피자", "치킨", "꿀"]
FASHION = ["신발", "바지", "옷", "청바지", "티셔츠", "운동화", "블라우스", "자켓", "재킷", "속옷",
           "데님", "슬립온", "구두", "코트", "스니커즈", "원피스", "수트", "여성화", "남성화", "샌들",
           "셔츠", "팬티", "브라", "슬리퍼", "숙녀복", "런닝화", "니트", "점퍼", "패딩", "스커트",
           "치마", "레깅스", "양말", "조끼", "가디건", "맨투맨", "후드", "정장", "부츠", "로퍼", "힐",
           "잠옷", "트렌치", "남방", "슬랙스", "팬츠", "아우터", "의류", "등산화", "골프화"]
# 키워드에 걸리지만 식품, 의류가 아닌 상품 (쌀통, 구강세정기 등)
NOT_GOODS = ["쌀통", "세정기", "청소기", "프라이어", "밥솥", "냄비", "마스크", "옷걸이", "신발장"]
# 주문 이후 문제 상황만 사례로 쓴다. 배송 카테고리에는 방송 중 주문 통화가 많이 섞여 있다.
ISSUE = ["반품", "교환", "환불", "취소", "불량", "파손", "변질", "상함", "하자", "누락", "오배송",
         "미배송", "지연", "배송일정", "배송확인", "배송조회", "배송문의", "도착", "사이즈", "수리",
         "AS", "불만", "회수", "착불", "배송비"]
# 본인 확인 턴: 사례 흐름과 관계없고 마스킹 값만 남는다
PII_INTENTS = ("고객정보", "전화번호", "성함", "성명", "주소", "본인", "생년월일")


def text_of(r):
    for k in ("고객질문(요청)", "고객답변", "상담사질문(요청)", "상담사답변"):
        if r.get(k):
            return r[k].strip()
    return ""


def products_of(r):
    out = []
    for kb in (r.get("지식베이스") or "").split(","):
        kb = kb.strip()
        if kb.endswith("/상품") or kb.endswith("/상품명"):
            out.append(kb.rsplit("/", 1)[0].strip())
    return out


def classify(products):
    if any(x in p for p in products for x in NOT_GOODS):
        return None
    joined = " ".join(products)
    food = any(k in joined for k in FOOD)
    fashion = any(k in joined for k in FASHION)
    if food == fashion:
        return None
    return "food" if food else "fashion"


def is_pii_turn(r, text):
    if any(k in (r.get("상담사의도") or "") for k in PII_INTENTS):
        return True
    masked = text.count("ㅇ")
    return masked >= 3 and masked / max(len(text.replace(" ", "")), 1) > 0.5


def dialogs(path):
    z = zipfile.ZipFile(path)
    recs = json.loads(z.read(z.namelist()[0]).decode("utf-8-sig"))
    grouped = collections.defaultdict(list)
    for r in recs:
        grouped[r["대화셋일련번호"]].append(r)
    del recs
    for did, rs in grouped.items():
        rs.sort(key=lambda r: int(r.get("문장번호") or 0))
        yield did, rs


def build(root: Path):
    OUT.mkdir(parents=True, exist_ok=True)
    files = {s: (OUT / f"{s}_cases.jsonl").open("w", encoding="utf-8") for s in ("food", "fashion")}
    stats = collections.Counter()
    intents = {s: collections.Counter() for s in files}
    for split_dir, split in SPLITS.items():
        for cat in CATEGORIES:
            hits = list((root / split_dir).glob(f"라벨링데이터_*/*_K쇼핑_{cat}_*.zip"))
            assert len(hits) == 1, (split_dir, cat, hits)
            for did, rs in dialogs(hits[0]):
                products = sorted({p for r in rs for p in products_of(r)})
                service = classify(products)
                stats[(split, cat, service or "skip")] += 1
                if not service:
                    continue
                turns, cust_intents = [], []
                for r in rs:
                    t = text_of(r)
                    if not t or is_pii_turn(r, t):
                        continue
                    turns.append({"speaker": r["화자"], "text": t})
                    if r.get("고객의도"):
                        cust_intents.append(r["고객의도"])
                if not any(k in i for i in cust_intents for k in ISSUE):
                    stats[(split, cat, service)] -= 1
                    stats[(split, cat, "no-issue")] += 1
                    continue
                first_q = next((x["text"] for x in turns
                                if x["speaker"] == "고객" and len(x["text"]) > 8), "")
                case = {"id": did, "split": split, "category": cat, "service": service,
                        "products": products, "customerIntents": sorted(set(cust_intents)),
                        "firstCustomerUtterance": first_q, "turns": turns}
                files[service].write(json.dumps(case, ensure_ascii=False) + "\n")
                for i in set(cust_intents):
                    intents[service][i] += 1
            print("done", split, cat, flush=True)
    for f in files.values():
        f.close()

    summary = {
        "counts": {f"{s}/{c}/{v}": n for (s, c, v), n in sorted(stats.items())},
        "topIntents": {s: intents[s].most_common(25) for s in intents},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return stats


if __name__ == "__main__":
    st = build(Path(sys.argv[1]))
    for svc in ("food", "fashion", "no-issue", "skip"):
        row = {f"{s}/{c}": st[(s, c, svc)] for s in SPLITS.values() for c in CATEGORIES}
        print(svc, sum(row.values()), row)

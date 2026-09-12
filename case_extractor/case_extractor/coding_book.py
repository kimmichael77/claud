"""판례분석 코딩시트의 변수 정의 (코딩북 시트 내용을 그대로 옮긴 것).

이 파일은 LLM 프롬프트 구성과 값 검증(validation)에 함께 쓰인다.
연구자가 코딩북을 수정하면 이 파일도 함께 업데이트해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldDef:
    name: str
    group: str
    definition: str
    rule: str
    status: str
    # 코드가 직접 계산하는 필드는 LLM에게 값을 요청하지 않는다.
    computed: bool = False
    # 연구자/시스템이 채우는 필드 (LLM에게 요청하지 않음)
    manual: bool = False


CODING_BOOK: list[FieldDef] = [
    FieldDef("case_id", "식별", "사건 고유 식별번호", "연구자 부여 (예: DF-2026-001)", "확정", manual=True),
    FieldDef("case_type", "식별/비교군", "사건 유형(핵심 비교변수)",
             "0=몰카(카메라등이용촬영, 제14조), 1=딥페이크(허위영상물, 제14조의2). 본 연구의 핵심 비교축", "확정"),
    FieldDef("start_date", "시간", "관찰 시작일", "공소제기일 기준, 불명 시 1심 최초 공판일 (YYYY-MM-DD)", "확정"),
    FieldDef("end_date", "시간", "관찰 종료일", "확정판결일 또는 자료수집 마감일(중도절단 시) (YYYY-MM-DD)", "확정"),
    FieldDef("duration", "시간", "처리기간(일)",
             "end_date - start_date. 코드가 자동 계산.", "확정", computed=True),
    FieldDef("event", "사건지시자", "확정판결 발생 여부", "1=확정, 0=중도절단(미확정)", "확정"),
    FieldDef("sentence_months", "종속변수(주)", "선고 형량(월 단위 환산)",
             "징역 1년2개월=14, 징역 2년6월=30. 집행유예도 징역형 기간을 기재(유예기간 아님). 벌금형은 결측(-99) 후 sentence_type으로 구분", "확정"),
    FieldDef("sentence_type", "종속변수(주)", "선고 형종",
             "1=실형, 2=집행유예, 3=벌금형, 4=기타(무죄·선고유예·면소·공소기각)", "확정"),
    FieldDef("prior_judgment_date", "종속변수(보조)", "원심(1심) 선고일 — 항소심 사건만 해당",
             "항소심 판결문의 '원심판결' 항목에 기재된 선고일. 1심 사건은 공란 (YYYY-MM-DD)", "확정"),
    FieldDef("appeal_duration", "종속변수(보조)", "상소심 소요기간(일)",
             "end_date(선고일) - prior_judgment_date. 항소심 사건만 계산 가능. 코드가 자동 계산.", "확정", computed=True),
    FieldDef("sentencing_guideline_type", "사건특성", "대법원 양형기준상 유형 (디지털성범죄 > 03. 허위영상물 등의 반포 등)",
             "1=제1유형(편집 등), 2=제2유형(반포 등), 3=제3유형(영리 목적 반포 등), 9=판결문 미기재", "확정"),
    FieldDef("guideline_min_months", "양형기준", "대법원 양형기준 권고형 범위의 하한(월)",
             "판결문 '양형기준에 따른 권고형의 범위'에 기재된 하한. 예: '징역 6월~1년 6월' → 6. 다수범죄 처리기준이 별도 제시된 경우 그 값을 우선 사용", "확정"),
    FieldDef("guideline_max_months", "양형기준", "대법원 양형기준 권고형 범위의 상한(월)",
             "위와 동일. '징역 6월~1년 6월' → 18", "확정"),
    FieldDef("guideline_area", "양형기준", "권고영역", "1=감경영역, 2=기본영역, 3=가중영역, 9=판결문 미기재", "확정"),
    FieldDef("guideline_deviation", "종속변수(핵심2)", "양형기준 권고범위 이탈 여부",
             "sentence_months가 guideline_min~max 밖이면 1, 내면 0, 미기재 9. 코드가 자동 계산.", "확정", computed=True),
    FieldDef("deviation_direction", "종속변수(핵심2)", "이탈 유형 (김한균, 2014 개념체계)",
             "0=범위내 중간영역, 1=진정하향이탈, 2=진정상향이탈, 3=부진정하향이탈(rel_position≤0.15), "
             "4=부진정상향이탈(rel_position≥0.85), 9=판단불가/양형기준 미기재. 코드가 자동 계산.", "확정", computed=True),
    FieldDef("guideline_rel_position", "종속변수(핵심2)", "권고형량범위 전체 기준 상대위치 (0=하한, 1=상한)",
             "(sentence_months - guideline_min) / (guideline_max - guideline_min). 코드가 자동 계산.", "확정", computed=True),
    FieldDef("area_min_months", "양형기준", "적용된 형량영역(감경/기본/가중)의 하한(월)",
             "판결문에 '[권고영역 및 권고형의 범위] 기본영역, 징역 6월~1년 6월'처럼 영역과 범위가 함께 기재된 경우 그 영역의 하한", "확정"),
    FieldDef("area_max_months", "양형기준", "적용된 형량영역의 상한(월)", "위와 동일", "확정"),
    FieldDef("area_rel_position", "종속변수(핵심2)", "해당 영역 기준 상대위치 (0=영역하한, 1=영역상한)",
             "(sentence_months - area_min) / (area_max - area_min). 코드가 자동 계산.", "확정", computed=True),
    FieldDef("aggravating_factors", "양형기준", "특별양형인자 중 가중요소 개수",
             "판결문 '[특별양형인자] 가중요소:' 항목의 개수. 없으면 0", "확정"),
    FieldDef("mitigating_factors", "양형기준", "특별양형인자 중 감경요소 개수",
             "판결문 '[특별양형인자] 감경요소:' 항목의 개수. 없으면 0", "확정"),
    FieldDef("offender_age", "가해자", "가해자 연령", "실수(만 나이)", "확정"),
    FieldDef("prior_record", "가해자", "전과 여부", "0=없음, 1=동종전과, 2=이종전과", "확정"),
    FieldDef("num_codefendants", "가해자", "공동피고인 수", "단독범=0, 정수", "확정"),
    FieldDef("offender_gender", "가해자", "가해자 성별", "0=남성, 1=여성", "확정"),
    FieldDef("num_victims", "피해자", "피해자 수", "정수 (다수 불특정 시 별도 처리)", "확정"),
    FieldDef("victim_relationship", "피해자", "가해자-피해자 관계",
             "1=지인,2=학교동급생,3=유명인,4=불특정,9=확인불가", "확정"),
    FieldDef("victim_minor", "피해자", "미성년 피해자 포함 여부", "0=성인만, 1=미성년 포함", "확정"),
    FieldDef("act_type", "사건특성", "행위 유형",
             "1=제작만, 2=제작+유포, 3=유포만(재유포), 4=소지·시청만, 5=영리목적 반포(제14조의2 제3항 적용)", "확정"),
    FieldDef("platform", "사건특성", "유통 플랫폼",
             "1=텔레그램,2=디스코드,3=기타SNS,4=온라인커뮤니티,5=해외성인사이트,9=확인불가", "확정"),
    FieldDef("forensic_evidence", "사건특성", "디지털포렌식 감정 실시 여부", "0=없음, 1=실시", "확정"),
    FieldDef("deletion_compliance", "사건특성", "삭제 이행 여부", "0=언급없음,1=자발적삭제,2=불이행", "확정"),
    FieldDef("law_period", "법적맥락", "법 개정 시점 구분", "1=2020.3 이전,2=2020.3~2024.9,3=2024.9 이후", "확정"),
    FieldDef("court_region", "법원", "관할법원 지역", "수도권/광역시/기타 (텍스트)", "확정"),
    FieldDef("instance", "법원", "심급", "1=1심,2=항소심,3=상고심", "확정"),
    FieldDef("coder_id", "관리", "코딩 담당자", "신뢰도 검증용 식별자. 실행 시 --coder-id 값으로 채움", "확정", manual=True),
    FieldDef("coding_note", "관리", "코딩 비고", "모든 변수의 코딩 근거 기재. '변수명=값: 판결문 원문 근거' 형식으로 줄바꿈 구분. 결측 항목은 이유 명시. LLM 특이사항 + 코드가 [AI 추출] 태그를 덧붙임", "확정"),
    FieldDef("distribution_purpose_established", "사건특성", "'반포 등을 할 목적으로' 요건 인정 여부 (한민경 2024)",
             "0=불인정/쟁점없음, 1=법원이 반포목적 인정. 무죄 사유가 이 요건 불충족인 경우 반드시 0으로 코딩하고 "
             "coding_note에 '반포목적 불인정으로 무죄' 명시", "가설(파일럿검증)"),
    FieldDef("unidentified_victims_exist", "피해자", "판결문에 특정된 피해자 외 미특정 다수 피해자 존재 여부",
             "0=없음(고소인만), 1=있음(불특정 다수 피해자 언급). num_victims는 특정된 인원만 코딩하고 이 변수로 보완", "가설(파일럿검증)"),
    FieldDef("fabrication_suspected_unconfirmed", "사건특성", "합성·편집이 의심되나 유죄로 확정되지 않은 사건 여부 (김중곤 2024 방식 참고)",
             "0=쟁점없음/정상확정, 1=판결문에 '합성 의심되나 증거불충분' 등으로 기재. 이 경우 event 코딩 시 무죄 확정으로 처리하되 "
             "별도 표기하여 민감도분석에 활용", "가설(파일럿검증)"),
    FieldDef("relationship_power_dynamic", "피해자", "가해자-피해자 관계의 위계적 성격 (Tittle 1995 통제균형이론 반영)",
             "0=대등한 지위(동창·친구 등), 1=가해자가 우월적 지위(직장상사·교사·단체간부 등), 9=관계 불명확. "
             "victim_relationship과 별도로 교차코딩", "가설(파일럿검증)"),
    FieldDef("digital_guardianship", "사건특성", "피해자의 디지털 보호요인 존재 여부 (일상생활이론의 보호 부재 개념을 디지털 맥락에 적용)",
             "0=보호요인 부재(SNS 전체공개, 피해자가 이미지 유출을 인지못함), 1=존재(비공개 계정임에도 유출, 지인 제보로 조기 인지 등). "
             "판결문에 언급 없으면 -99(결측) 처리", "가설(파일럿검증)"),
]

# 코딩시트 헤더 순서 (AR열까지, 마지막 '입력 안내' 열은 프로그램이 쓰지 않는다 — 사람이 남긴 메모용)
SHEET_COLUMN_ORDER: list[str] = [
    "case_id", "case_type", "start_date", "end_date", "duration", "event",
    "sentence_months", "sentence_type", "prior_judgment_date", "appeal_duration",
    "sentencing_guideline_type", "guideline_min_months", "guideline_max_months",
    "guideline_area", "guideline_deviation", "deviation_direction", "guideline_rel_position",
    "area_min_months", "area_max_months", "area_rel_position", "aggravating_factors",
    "mitigating_factors", "offender_age", "prior_record", "num_codefendants",
    "offender_gender", "num_victims", "victim_relationship", "victim_minor", "act_type",
    "platform", "forensic_evidence", "deletion_compliance", "law_period", "court_region",
    "instance", "coder_id", "coding_note", "distribution_purpose_established",
    "unidentified_victims_exist", "fabrication_suspected_unconfirmed",
    "relationship_power_dynamic", "digital_guardianship",
]

FIELDS_BY_NAME: dict[str, FieldDef] = {f.name: f for f in CODING_BOOK}

# LLM에게 실제로 값을 요청할 필드 (계산/수동 필드 제외)
LLM_REQUESTED_FIELDS: list[str] = [
    name for name in SHEET_COLUMN_ORDER
    if not FIELDS_BY_NAME[name].computed and not FIELDS_BY_NAME[name].manual
]

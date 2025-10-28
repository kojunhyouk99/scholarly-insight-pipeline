# arXiv Trend Research 논문 트렌드 분석 파이프라인

이 프로젝트는 Cornell University와 파트너들이 Kaggle에 공개한 **arXiv 학술 메타데이터**(1.7M+ STEM 논문 메타 정보)를 입력으로 받아, 월별 업로드 추세·카테고리별 성장률·변동성 지표를 자동 계산하고 **한 장짜리 인사이트 리포트**까지 생성하는 엔드투엔드 파이프라인입니다. JSON 스냅샷(`project/data/arxiv-metadata-oai-snapshot.json`)만 준비하면 스트리밍 집계 → 통계 분석 → 시각화 → PDF/텍스트 보고서가 한 번에 만들어집니다.

## Dataset

- **출처**: Cornell University가 운영하는 arXiv.org를 Kaggle에서 미러링한 `arxiv-metadata-oai-snapshot.json` (약 4.9GB).  
- **포함 항목**: `id`, `title`, `authors`, `abstract`, `categories`, `versions[].created`, `update_date` 등 각 논문의 핵심 메타데이터.  
- **규모**: STEM 전 분야 논문 170만 편 이상(매주 업데이트).  
- **주요 활용**: 트렌드 분석, 추천 시스템, 카테고리 분류, 인용 네트워크, 지식 그래프, 시맨틱 검색 등.  
- **라이선스**: 메타데이터는 Creative Commons CC0 1.0 (Public Domain). 개별 논문 전문은 arXiv 라이선스를 따릅니다.  
- **참고 링크**:  
  - Kaggle: *arXiv Dataset* (Cornell University and collaborators)  
  - GCS: `gs://arxiv-dataset` (PDF 원문 일괄 접근 가능)  
- **NOTE**: 본 프로젝트는 메타데이터 중심 분석이며, 개별 논문 본문이나 PDF는 다운로드하지 않습니다.

## Pipeline Overview

1. **데이터 집계 (`scripts/01_stream_aggregate.py`)**  
   - 대용량 JSON을 반복자로 읽어 메모리 사용을 최소화합니다.  
   - `year_month × main_category` 조합별 업로드 수를 계산하여 `data/arxiv_monthly.csv`로 저장합니다.  
   - `--prefix cs.` 등으로 카테고리 prefix 필터를 적용할 수 있고, `--since 2015-01`처럼 특정 시점 이후만 집계할 수 있습니다.

2. **시각화 및 통계 요약 (`scripts/02_make_figures.py`)**  
   - 월별 업로드 추세(6/12개월 이동평균 포함), 카테고리 성장률, 업로드 볼륨, 변동성, 성장률 vs 규모 산점도, 최근 24개월 히트맵을 PNG로 생성합니다.  
   - 동시에 `data/arxiv_category_stats.csv`, `data/arxiv_summary.json`, `reports/trend_summary.txt`를 만들어 리포트에 필요한 수치를 즉시 활용할 수 있습니다.

3. **PDF 요약 (`scripts/03_export_onepager.py`)**  
   - 영어 하이라이트, Key Metrics 패널, 상·하위 카테고리 섹션과 6개 그래프를 A4 가로 한 장에 배치한 `report_onepager.pdf`를 자동 작성합니다.

## Automated Report Output

`python scripts/02_make_figures.py` → `python scripts/03_export_onepager.py` 실행만으로 다음 콘텐츠가 채워진 보고서를 얻을 수 있습니다.

- **Highlights**: 최신 월, 12개월 업로드, YoY 증감, 이동평균, 추세 기울기, 5년 CAGR, 시즌 피크/저점을 자동 계산해 bullet으로 정리합니다. 예) `Latest month: 2025-10`, `YoY change: +12.65% (+30,269)`.
- **Key Metrics 패널**: 12M 업로드, 이동평균(6/12M), 시즌 피크/저점, 추세 기울기(증감률), 5Y CAGR 등을 카드 형태로 제공합니다.
- **카테고리 랭킹**: 성장률 Top, 볼륨 Top, 감소 카테고리, 변동성 Top을 텍스트로 나열해 그래프와 함께 비교할 수 있습니다.
- **시각화 6종**: 월별 추세(롤링 평균 포함), 성장률 Top-N, 볼륨 Top-N, 24개월 카테고리 히트맵, 성장률 vs 규모 산점도, 변동성 Top 그래프를 한 페이지에 배치합니다.
- **데이터 푸터**: Kaggle `arXiv Dataset` 출처, 메타데이터 범위(제목·저자·초록·카테고리·버전), CC0 라이선스를 명시하여 바로 외부 공유가 가능합니다.

PDF 예시 헤드라인:

```
arXiv Research Trend Summary (Last 12 Months)
• Latest month: 2025-10
• 12M uploads vs prior: 269,608 vs 239,339
• YoY change: +12.65% (+30,269)
• Rolling avg (6/12M): 23,582 / 22,467
• Trend slope: +235.4 papers/mo (+1.19%)
• 5Y CAGR: +9.10%
• Seasonality: peak Oct · low Jan
```

보고서는 위와 같은 하이라이트와 함께 카테고리별 랭킹, 6종 그래프, 데이터 출처가 한 장에 정리되어 면접/지원서 자료, 리서치 브리핑, 투자 리서치 등 데이터 기반 문서 작업에 즉시 활용할 수 있습니다.

## Quick Start

```bash
pip install -r requirements.txt

# 1. 월별 × 카테고리 집계 생성
python scripts/01_stream_aggregate.py --data data/arxiv-metadata-oai-snapshot.json

# 2. 시각화
python scripts/02_make_figures.py

# 3. PDF 요약
python scripts/03_export_onepager.py
```

### Useful Options

- `python scripts/01_stream_aggregate.py --prefix cs.` → 컴퓨터과학 카테고리만 집계  
- `python scripts/01_stream_aggregate.py --since 2015-01` → 2015년 1월 이후만 대상  
- `python scripts/02_make_figures.py --top-growth 20 --top-share 12` → Top-N 크기 조정  
- `python scripts/02_make_figures.py --heatmap-top 30 --heatmap-months 36` → 히트맵 범위 확대  
- `python scripts/03_export_onepager.py --out outputs/cs_report.pdf` → PDF 경로 커스터마이즈

각 스크립트는 `--help` 옵션으로 매개변수를 확인할 수 있습니다.

## Project Layout

```
project/
  data/
    arxiv-metadata-oai-snapshot.json    # 원본 Kaggle JSON
    arxiv_monthly.csv                   # [생성] 월별 × 메인 카테고리 집계
    arxiv_last12_pivot.csv              # [생성] 최근 12개월 pivot (Optional)
    arxiv_category_stats.csv            # [생성] 카테고리 통계 지표
    arxiv_summary.json                  # [생성] 전체 통계 요약
  figures/                              # [생성] PNG 결과
    01_monthly_total.png
    02_top_growth.png
    03_top_share.png
    04_category_heatmap.png
    05_growth_vs_volume.png
    06_volatility.png
  scripts/
    01_stream_aggregate.py
    02_make_figures.py
    03_export_onepager.py
    analysis_utils.py
  reports/
    trend_summary.txt                   # [생성] 텍스트 기반 하이라이트
  README.md
  requirements.txt
  report_onepager.pdf                   # [생성] 한 장 요약 PDF
```

## Tips

- JSON이 수 GB 수준일 때도 메모리 급증 없이 실행할 수 있도록 스트리밍 파서를 사용합니다.  
- PDF 생성 전 `figures/` 아래 PNG가 모두 존재하는지 확인하세요. 누락된 그림은 자동으로 건너뛰지만 빈 공간이 생길 수 있습니다.  
- 시각화 시 시스템에 한글 폰트가 없으면 기본 폰트로 대체됩니다. 한글 출력이 필요하다면 AppleGothic / Malgun Gothic / NanumGothic / Noto Sans CJK 계열 폰트를 설치해 주세요.  
- `reports/trend_summary.txt`는 최종 보고서 작성 시 바로 붙여넣기 좋은 주요 수치와 순위를 포함합니다.

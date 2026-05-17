"""Generate initial queries for SLR calibration."""
from research_finder.input_store import InputStore
from research_finder.extractor.keyword_extractor import KeywordExtractor
import yaml

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
cfg["embedding"]["provider"] = "api"

store = InputStore(cfg)
emb, text = store.load("Seeds of Green_Methodology")

extractor = KeywordExtractor(cfg)
queries = extractor.extract(text)

print(f"Generated {len(queries)} queries:")
for i, q in enumerate(queries, 1):
    print(f"  {i}. {q}")

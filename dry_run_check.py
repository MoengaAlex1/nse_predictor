import sys
sys.path.insert(0, 'pipeline')
from scripts.run_inference import run_company
from config import load_companies

companies = load_companies()
scom = next(c for c in companies if c['ticker'] == 'SCOM.NR')
print(f"Running inference for: {scom['ticker']} - {scom['name']}")
result = run_company(scom)
if result:
    print('Signal:', result['snapshot']['signal'])
    print('Price:', result['snapshot']['current_price_KES'])
    print('Technicals keys:', list(result['technicals'].keys())[:5])
    print('SUCCESS')
else:
    print('FAILED — run_company returned None (CSV likely not found)')

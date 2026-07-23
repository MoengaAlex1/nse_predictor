import re

with open('pipeline/scripts/scrape_nse_prices.py', encoding='utf-8') as f:
    src = f.read()

# Slice the source between the list declaration and _nse_cache to avoid
# pulling in unrelated tuples from other parts of the file.
start = src.find('_NSE_NAME_TO_BASE')
end   = src.find('_nse_cache', start)
section = src[start:end]

pairs = re.findall(r'\("([^"]+)"\s*,\s*"([^"]+)"\)', section)

def name_to_base(display_name):
    name_lc = display_name.lower()
    for keyword, base in pairs:
        if keyword in name_lc:
            return base
    return None


# All companies seen on the NSE AJAX endpoint, grouped by sector.
# Format: (sector_code, ajax_display_name, expected_ticker_base)
ajax_companies = [
    # bank
    ('bank', 'ABSA Bank Kenya Plc Ord 0.50',                'ABSA'),
    ('bank', 'Bank of Kigali',                              'BKG'),
    ('bank', 'Diamond Trust Bank Kenya Ltd Ord 4.00',       'DTK'),
    ('bank', 'Equity Group Holdings Plc Ord 0.50',          'EQTY'),
    ('bank', 'FAMILY BANK LIMITED',                         'FMLY'),
    ('bank', 'HF Group Plc Ord 5.00',                       'HFCK'),
    ('bank', 'I&M Holdings Plc Ord 1.00',                   'IMH'),
    ('bank', 'Kenya Commercial Bank Ltd Ord 1.00',          'KCB'),
    ('bank', 'NCBA Group Plc 0rd 5.00',                     'NCBA'),
    ('bank', 'Stanbic Holdings Ltd ord.5.00',               'SBIC'),
    ('bank', 'Standard Chartered Bank Kenya Ltd Ord 5.00',  'SCBK'),
    ('bank', 'The Co-operative Bank of Kenya Ltd Ord 1.00', 'COOP'),
    ('bank', 'National Bank of Kenya Ltd Ord 5.00',         None),   # delisted / acquired by KCB
    ('bank', 'Nairobi Business Ventures Ltd',               'NBV'),
    # agric
    ('agric', 'Eaagads Ltd Ord 1.25',                       'EGAD'),
    ('agric', 'Kakuzi Ord.5.00',                            'KUKZ'),
    ('agric', 'Kapchorua Tea Co. Ltd Ord Ord 5.00',         'KAPC'),
    ('agric', 'Limuru Tea Co. Ltd Ord 20.00',               'LIMT'),
    ('agric', 'Sasini Ltd Ord 1.00',                        'SASN'),
    ('agric', 'Williamson Tea Kenya Ltd Ord 5.00',          'WTK'),
    ('agric', 'Africa Mega Agri Corp PLc 5.00',             'AMAC'),
    # auto
    ('auto', 'Car and General (K) Ltd Ord 5.00',            'CGEN'),
    ('auto', 'Sameer Africa Ltd Ord 5.00',                  'SMER'),
    # const
    ('const', 'Athi River Mining Ord 5.00',                 None),   # in receivership / delisted
    ('const', 'Bamburi Cement Ltd Ord 5.00',                None),   # taken private / delisted 2023
    ('const', 'B.O.C Kenya Ltd Ord 5.00',                   'BOC'),
    ('const', 'Carbacid Investments Ltd Ord 5.00',          'CARB'),
    ('const', 'Crown Berger Ltd 0rd 5.00',                  'CRWN'),
    ('const', 'E.A.Cables Ltd Ord 0.50',                    None),   # suspended / delisted
    ('const', 'E.A.Portland Cement Ltd Ord 5.00',           'PORT'),
    # comm
    ('comm', 'Deacons (East Africa) Plc Ord 2.50',          None),   # in administration / not tracked
    ('comm', 'Eveready East Africa Ltd Ord.1.00',           'EVRD'),
    ('comm', 'Express Ltd Ord 5.00',                        'XPRS'),
    ('comm', 'Home Afrika Ltd Ord 1.00',                    'HAFR'),
    ('comm', 'Homeboyz Entertainment Plc',                  None),   # not tracked
    ('comm', 'Kenya Airways Ltd Ord 5.00',                  'KQ'),
    ('comm', 'Longhorn Kenya Ltd 1.00',                     'LKL'),
    ('comm', 'Nation Media Group Ord. 2.50',                'NMG'),
    ('comm', 'Nairobi Securities Exchange 4.00',            'NSE'),
    ('comm', 'Scangroup  Ltd Ord 1.00',                     'SCAN'),
    ('comm', 'Standard Group  Ltd Ord 5.00',                'SGL'),
    ('comm', 'TPS Eastern Africa (Serena) Plc Ord 1.00',    'TPSE'),
    ('comm', 'Uchumi Supermarket Ltd Ord 5.00',             'UCHM'),
    # energy
    ('energy', 'KenGen Ltd  Ord. 2.50',                     'KEGN'),
    ('energy', 'Kenya Pipeline Company',                    'KPC'),
    ('energy', 'Kenya Power Lighting  Co Plc Ord 20.00',    'KPLC'),
    ('energy', 'Total Kenya Ltd Ord 5.00',                  'TOTL'),
    ('energy', 'Umeme Ltd Ord 0.50',                        'UMME'),
    # insr
    ('insr', 'British-American Investments Ord 0.10',       'BRIT'),
    ('insr', 'CIC Insurance Group Plc Ord 1.00',            'CIC'),
    ('insr', 'Jubilee Holdings Ltd Ord 5.00',               'JUB'),
    ('insr', 'Kenya Re-Insurance Corporation Ltd Ord 2.50', 'KNRE'),
    ('insr', 'Liberty Insurance',                           'LBTY'),
    ('insr', 'Sanlam  Insurance Holdings Ltd 0rd 5.00',     'SLAM'),
    # invest
    ('invest', 'Centum Investment Co Ltd Ord 0.50',         'CTUM'),
    ('invest', 'Kurwitu Ventures',                          'KURV'),
    ('invest', 'Olympia Capital Holdings ltd Ord 5.00',     'OCH'),
    ('invest', 'Trans-Century Ltd Ord 0.50',                'TRFC'),
    # manu
    ('manu', 'B.O.C Kenya Ltd Ord 5.00',                    'BOC'),
    ('manu', 'British American Tobacco Kenya Ltd Ord 10.00','BAT'),
    ('manu', 'East African Breweries PLC Ord 2.00',         'EABL'),
    ('manu', 'Flame Tree Group Holdings Ltd Ord 0.825',     None),   # not tracked
    ('manu', 'Mumias Sugar Co. Ltd Ord 2.00',               None),   # not tracked / suspended
    ('manu', 'Shri Krishana Overseas',                      None),   # not tracked
    ('manu', 'Unga Group Plc Ord 5.00',                     'UNGA'),
    # tele
    ('tele', 'Safaricom Ltd Ord 0.05',                      'SCOM'),
    # real
    ('real', 'ALP Industrial I-REIT',                       'ALP'),
    ('real', 'Laptrust Imara I-REIT',                       None),   # not tracked (LKL used for Longhorn)
    ('real', 'Trific Green USD IREIT',                      'TRFC'),
    # investse
    ('investse', 'Nairobi Securities Exchange 4.00',        'NSE'),
    # exchange
    ('exchange', 'New Gold Issuer (RP) Ltd',                'GLD'),
    ('exchange', 'Satrix MSCI World Feeder ETF',            'SMWF'),
    # trans
    ('trans', 'TPS Eastern Africa (Serena) Plc Ord 1.00',  'TPSE'),
]

print('%-6s  %-10s  %-10s  %s' % ('STATUS', 'GOT', 'EXPECTED', 'AJAX NAME'))
print('-' * 90)
gaps = []
for sector, ajax_name, expected in ajax_companies:
    result = name_to_base(ajax_name)
    if result == expected:
        status = 'OK'
    elif expected is None:
        # Not tracked — we expect no match; warn only if we accidentally match something
        status = 'SKIP' if result is None else 'EXTRA'
    else:
        status = 'MISS' if result is None else 'WRONG'

    if status not in ('OK', 'SKIP'):
        print('%-6s  %-10s  %-10s  [%s] %s' % (
            status, result or '(none)', expected or '(none)', sector, ajax_name))
        gaps.append((status, sector, ajax_name, expected, result))

ok_count   = sum(1 for s, *_ in [(sector, ajax_name, expected)
                                  for sector, ajax_name, expected in ajax_companies
                                  if name_to_base(ajax_name) == expected])
print()
print(f'Mapped OK : {ok_count} / {len(ajax_companies)}')
print(f'Gaps      : {len(gaps)}')
if not gaps:
    print('All AJAX names map correctly.')

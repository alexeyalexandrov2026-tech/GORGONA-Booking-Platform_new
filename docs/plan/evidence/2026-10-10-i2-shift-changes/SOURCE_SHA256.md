# I2 source snapshot — SHA256 before the final full suite

Raw working-copy bytes; Git normalizes line endings separately.
PASS: all16 API files match before and after the final full validation
(1380 passed / 4 skipped / 738.66s) and match the independent reviewer snapshot.

| File | SHA256 |
|---|---|
| api/src/gorgona_booking/api/app.py | 66E23559116378FF6E52EFC47FB8053EF1ADBEFF5D74BB6744DDF27CBC228B22 |
| api/src/gorgona_booking/api/shift_changes.py | 7B4AF5397567EC2046C0EA6BCA7290632A9C09A775C920125CD17F1311090BE8 |
| api/src/gorgona_booking/business/shift_change_contracts.py | 62EA6F39FE7F617C1C7E86CBF698A0DD9FCF35396E4E202F79F9AA175D32340D |
| api/src/gorgona_booking/business/shift_changes.py | 34CE3E5CAE15EB8E678B44FB41829858D2B5212AC8A331396AA411FB3D097CDD |
| api/src/gorgona_booking/business/workforce.py | 820C5F12D97B663D838952F2AECD80CB6FCF2A5B14ABFFCBC0E1D155EC5FD6D0 |
| api/src/gorgona_booking/db/migrations/0033_shift_changes.sql | 5A5F7408E78C294D2AE2A06A88B605DB25CE8221D254AB387B328FD753230CEB |
| api/src/gorgona_booking/db/workforce_guard.py | 8C6D2BDABC8341366F2B9B15B5A562DAA483459AFEE10EBB2C0ADBC1E66B517C |
| api/tests/integration/test_location_access.py | D55647A25F8BC6C583FCEF401118983996E959C9F330EF14A3B8C419BD4FE915 |
| api/tests/integration/test_shift_changes_guards.py | 2D34EA7521E1FF90BB124A234C44A99C1FD822935610F54F439BC8BA309B2437 |
| api/tests/integration/test_shift_changes_races.py | 700A1C5177153D0CE11B053986E8542C2CDF9227204A14AB0EF52178C0D075A6 |
| api/tests/integration/test_shift_changes_schema.py | 4DF287F2BBC9ED3F19F639B3947F56DFFAA2942A803E0A741704896AC694087F |
| api/tests/integration/test_shift_changes_upgrade.py | 809897CEBDD75F9A9D84C30D7B3C3808334164E07F7AB41E61A95D74716C8F52 |
| api/tests/integration/test_shift_changes.py | 081ABCA3CE09484261D2026106119367599164C914735A2A8AE7D62EBF3BE6C0 |
| api/tests/integration/test_workforce_guards.py | 79E7E332BF696BCEA862502F5B47FB1A1B40A0B722E5E99BD1D2F85145015757 |
| api/tests/integration/test_workforce_upgrade.py | 878FA7F329B770C184B7DC3814AFBC7BF72144BACD31ACCD99A7408F0CEF5CCB |
| api/tests/unit/test_shift_change_contracts.py | B2EA4D89700F258C35F0CDE70E11B4FB2A53FE151686299FD89985A41342092E |

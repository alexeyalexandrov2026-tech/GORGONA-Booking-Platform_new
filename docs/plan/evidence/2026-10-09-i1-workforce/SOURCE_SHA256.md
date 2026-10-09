# I1 reviewed API snapshot

SHA256 of the canonical source and tests exercised by final local validation.
These are executor file byte hashes before Git CRLF-to-LF normalization; all
21 staged API blobs separately matched the validated files after normalization.
Historical migrations 0001-0031, module/readiness registry and web source have no diff.

| File | SHA256 |
|---|---|
| api/src/gorgona_booking/api/app.py | D40A6574B5B51EC56951645ACF91A97AA2F2807FFBA72EDA37436C679A4DFC93 |
| api/src/gorgona_booking/api/salons.py | 0DEF2B05961012DAEEEAEB0587ED12B6302E954EA04FFAB7BF0D8C496B8F486B |
| api/src/gorgona_booking/api/workforce.py | 551DE1004FE1AEBEE2753E756B5EF29F1965271BDB86D8419909FC7D1A9B8D78 |
| api/src/gorgona_booking/auth/permissions.py | 4E6774CF0A3B3FDEB59E8AF9658324C37D7A55710EAD3080A769BF99CBFF517B |
| api/src/gorgona_booking/booking/repository.py | F582A62A1F250A25ACE4F802BD513FB8EEDDCC1570F88CB1CF0EBC10E4CEE20E |
| api/src/gorgona_booking/business/workforce_contracts.py | 8F6B313BF8AEFD02F83F8BEF7A94AB66A3481ED1D2647409DAB42CD5BC249710 |
| api/src/gorgona_booking/business/workforce.py | FE0E0381717AC3A5CC6AF38A01367F499229AC8838480DACEA69A472E86D76D0 |
| api/src/gorgona_booking/db/migrations/0032_workforce.sql | DAD200C8C54F64A38020B27415ABB082D9E4D81A5690B6D6621A8971AAD9427D |
| api/src/gorgona_booking/db/schema_guard.py | 8FB15F22994F020B3A300F6EA6A66AE98A716DB3D2AFBAFC1EA5D1503095BB73 |
| api/src/gorgona_booking/db/workforce_guard.py | 31B769049D2CFB1F5B7B8884FD21015E6FF25DC658C5DC07FE1968FD131E8595 |
| api/src/gorgona_booking/occupancy/reservations.py | 12BE9520FE826096311B61D2F2E7BD595DF99C1CFCA33E1B8DEA0315EA8B8D6D |
| api/src/gorgona_booking/onboarding/service.py | 39D141B5D609088F7998771D21022FEA9F0B94EF6DB502EDABEFFC294A0BC4EF |
| api/tests/integration/test_h3_upgrade.py | 050EB8B7E20E765E40954C14C4C1EDF2433B24AA37C70DE73D837E1FAB028C69 |
| api/tests/integration/test_location_access.py | 8CB865261E90F148498C7BE94867F9A136F226682D848C5870436A48A6436489 |
| api/tests/integration/test_provider_admission_upgrade.py | 1AB37AEF399ED958882A53975CDF5080775C1243272CA513E9E1A3A933B22033 |
| api/tests/integration/test_resource_kind_boundaries.py | 77ABAFF1149950FC764FBFFD65A834670ABA5663579EC5987E1F9BDEBF929933 |
| api/tests/integration/test_workforce_guards.py | ED63D9ED30016881AA35AE361B288FC3DC63475A0936CC043E7E6D54AE5314EB |
| api/tests/integration/test_workforce_upgrade.py | F5D6FEBD825B1D790EE453595934A1B1C29A9BC6864CFCDF9BE6042E2B4936EB |
| api/tests/integration/test_workforce.py | 8AFCE9F987B5EA06013AAC558647DF634480B5F0CB986BFE0199067CA0D43EED |
| api/tests/unit/test_counterparty_contracts.py | F22EC946F89847F6FEC1181EC2E2CD0D8D443CB0A2C14208BAFDF4FD12B1063E |
| api/tests/unit/test_workforce_contracts.py | 6FFD62C33F6DC663BA859B94AC379B135D7B889F3265D328C01714DDC83A4D4C |

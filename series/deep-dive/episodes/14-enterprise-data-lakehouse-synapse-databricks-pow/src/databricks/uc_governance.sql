-- Needs a Unity Catalog workspace (Premium). Not executed in this folder: no local engine runs Unity Catalog.
-- Catalog and schema names are the lab's; the groups are account groups you create in the lab.
CREATE OR REPLACE FUNCTION lakehouse.gold.region_filter(region STRING)
RETURN is_account_group_member('contoso-global') OR (region = 'emea' AND is_account_group_member('contoso-emea'));

ALTER TABLE lakehouse.gold.daily_sales SET ROW FILTER lakehouse.gold.region_filter ON (region);

CREATE OR REPLACE FUNCTION lakehouse.gold.mask_key(customer_key STRING)
RETURN CASE WHEN is_account_group_member('contoso-global') THEN customer_key ELSE concat(left(customer_key, 6), '...') END;

ALTER TABLE lakehouse.gold.customer_summary ALTER COLUMN customer_key SET MASK lakehouse.gold.mask_key;

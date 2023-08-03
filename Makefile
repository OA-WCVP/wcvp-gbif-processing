wcvp_zip_url=http://sftp.kew.org/pub/data-repositories/WCVP/Special_Issue_28_Feb_2022/wcvp_names_and_distribution_special_issue_28_feb_2022.zip
gbif_taxonomy_url=https://hosted-datasets.gbif.org/datasets/backbone/current/backbone.zip
tdwg_wgsrpd_l3_url=https://github.com/jiacona/tdwg-geojson/raw/master/tdwg-level3.geojson
ih_url="http://sweetgum.nybg.org/science/api/v1/institutions/search?dateModified=%3E01/01/2000&download=yes"
geonames_capital_cities_url=http://download.geonames.org/export/dump/cities15000.zip
gadm_gpkg_url=https://geodata.ucdavis.edu/gadm/gadm4.1/gadm_410-levels.zip

python_launch_cmd=winpty python
python_launch_cmd=python

date_formatted=$(shell date +%Y%m%d-%H%M%S)

username=YOUR_GBIF_USERNAME
password=YOUR_GBIF_PASSWORD

# limit_args can be used in any step that reads a data file (ie explode and link) 
# It will reduce the number of records processed, to ensure a quick sanity check of the process
#limit_args= --limit=100000
#limit_args=
wget_args=--quiet

downloads/wcvp.zip:
	mkdir -p downloads
	wget $(wget_args) -O $@ $(wcvp_zip_url)

# Download WCVP taxonomy
downloads/wcvp_names.txt: downloads/wcvp.zip
	unzip -p $^  wcvp_names.txt >$@
getwcvp: downloads/wcvp_names.txt

# Download WCVP distributions
downloads/wcvp_distribution.txt: downloads/wcvp.zip
	unzip -p $^  wcvp_distribution.txt >$@
getwcvpdist: downloads/wcvp_distribution.txt

# Download GBIF taxonomy
downloads/gbif-taxonomy.zip:
	mkdir -p downloads
	wget $(wget_args) -O $@ $(gbif_taxonomy_url)
getgbif: downloads/gbif-taxonomy.zip

# Download TDWG WGSRPD L3 as geojson
downloads/tdwg_wgsrpd_l3.json:
	mkdir -p downloads
	wget $(wget_args) -O $@ $(tdwg_wgsrpd_l3_url)

# Download IH datafile
downloads/ih.txt:
	mkdir -p downloads
	wget $(wget_args) -O $@ $(ih_url)

# Download geonames capital cities
downloads/cities15000.zip:
	mkdir -p downloads	
	wget $(wget_args) -O $@ $(geonames_capital_cities_url)

# Download GADM file
downloads/gadm_410-gpkg.zip:
	mkdir -p downloads
	wget $(wget_args) -O $@ $(gadm_gpkg_url)

downloads/gadm_410-levels.gpkg: downloads/gadm_410-gpkg.zip
	mkdir -p downloads
	unzip $^ -d downloads
	touch $@
    
dl: downloads/wcvp_names.txt downloads/wcvp_distribution.txt downloads/gbif-taxonomy.zip downloads/tdwg_wgsrpd_l3.json downloads/gadm_410-levels.gpkg

# Extract taxon file from GBIF backbone taxonomy
data/Taxon.tsv: downloads/gbif-taxonomy.zip
	mkdir -p data
	unzip -d data -uj  downloads/gbif-taxonomy.zip backbone/Taxon.tsv
	# Extracted file will have original mod date - so touch to update
	touch data/Taxon.tsv

# Filter GBIF backbone taxonomy for Tracheophyta
data/Taxon-Tracheophyta.tsv: filtergbif.py data/Taxon.tsv
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) --removeHybrids $@
filter: data/Taxon-Tracheophyta.tsv

# Process GBIF and WCVP taxonomies
data/gbif2wcvp.csv: gbif2wcvp.py data/Taxon-Tracheophyta.tsv downloads/wcvp_names.txt
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) $@

# Download GBIF occurrences with type status
data/gbif-type-download.id: resources/gbif-type-specimen-download.json
	curl -s --include --user ${username}:${password} --header "Content-Type: application/json" --data @$^ https://api.gbif.org/v1/occurrence/download/request > $@

getdownloadstatus: data/gbif-type-download.id
	curl -Ss https://api.gbif.org/v1/occurrence/download/$(shell cat $^) | jq .

# data/gbif-types.zip: data/gbif-type-download.id
# 	# Get download ID from file
# 	$(eval download_id:=$(shell cat $^))
# 	# Get download link from occurrence download service
# 	# Will jq throw an error if downloadLink is not found?
# 	$(eval download_link:=$(shell curl -Ss https://api.gbif.org/v1/occurrence/download/$(download_id) | jq '.downloadLink'))
# 	# wget it
# 	wget $(wget_args) -O $@ $(download_link)

gbif_download_url=https://api.gbif.org/v1/occurrence/download/request/0429412-210914110416597.zip

data/gbif-types.zip: 
	# wget it
	wget $(wget_args) -O $@ $(gbif_download_url)

# Process GBIF type data to add details of publishing organisation
data/gbif-typesloc.zip: types2publisherlocations.py data/gbif-types.zip downloads/ih.txt downloads/cities15000.zip
	$(python_launch_cmd) $^ $(limit_args) $@


###############################################################################
# All types

# Analyse how many taxa have type material in GBIF
data/taxa2gbiftypeavailability.csv data/taxa2gbiftypeavailability.yaml: taxa2gbiftypeavailability.py data/gbif2wcvp.csv data/gbif-types.zip
	$(python_launch_cmd) $^ $(limit_args) data/taxa2gbiftypeavailability.csv data/taxa2gbiftypeavailability.yaml

# Analyse how many taxa have type material published from within native range
data/taxa2nativerangetypeavailability.csv data/taxa2nativerangetypeavailability.yaml: taxa2nativerangetypeavailability.py data/gbif2wcvp.csv downloads/wcvp_distribution.txt data/gbif-types.zip data/gbif-typesloc.zip downloads/gadm_410-levels.gpkg downloads/tdwg_wgsrpd_l3.json
	$(python_launch_cmd) $^ $(limit_args) data/taxa2nativerangetypeavailability.csv data/taxa2nativerangetypeavailability.yaml

###############################################################################
# Post-CBD

cbd_impl_year:=1992

# Analyse how many taxa have type material in GBIF
data/taxa2gbiftypeavailability-cbd.csv data/taxa2gbiftypeavailability-cbd.yaml: taxa2gbiftypeavailability.py data/gbif2wcvp.csv data/gbif-types.zip
	$(python_launch_cmd) $^ $(limit_args) --year_min=$(cbd_impl_year)  data/taxa2gbiftypeavailability-cbd.csv data/taxa2gbiftypeavailability-cbd.yaml

# Analyse how many taxa have type material published from within native range
data/taxa2nativerangetypeavailability-cbd.csv data/taxa2nativerangetypeavailability-cbd.yaml: taxa2nativerangetypeavailability.py data/gbif2wcvp.csv downloads/wcvp_distribution.txt data/gbif-types.zip data/gbif-typesloc.zip downloads/gadm_410-levels.gpkg downloads/tdwg_wgsrpd_l3.json
	$(python_launch_cmd) $^ $(limit_args)  --year_min=$(cbd_impl_year) data/taxa2nativerangetypeavailability-cbd.csv data/taxa2nativerangetypeavailability-cbd.yaml

###############################################################################
# Post-Nagoya

nagoya_impl_year:=2014

# Analyse how many taxa have type material in GBIF
data/taxa2gbiftypeavailability-nagoya.csv data/taxa2gbiftypeavailability-nagoya.yaml: taxa2gbiftypeavailability.py data/gbif2wcvp.csv data/gbif-types.zip
	$(python_launch_cmd) $^ $(limit_args)  --year_min=$(nagoya_impl_year) data/taxa2gbiftypeavailability-nagoya.csv data/taxa2gbiftypeavailability-nagoya.yaml

# Analyse how many taxa have type material published from within native range
data/taxa2nativerangetypeavailability-nagoya.csv data/taxa2nativerangetypeavailability-nagoya.yaml: taxa2nativerangetypeavailability.py data/gbif2wcvp.csv downloads/wcvp_distribution.txt data/gbif-types.zip data/gbif-typesloc.zip downloads/gadm_410-levels.gpkg downloads/tdwg_wgsrpd_l3.json
	$(python_launch_cmd) $^ $(limit_args) --year_min=$(nagoya_impl_year) data/taxa2nativerangetypeavailability-nagoya.csv data/taxa2nativerangetypeavailability-nagoya.yaml


all: data/taxa2gbiftypeavailability.yaml data/taxa2nativerangetypeavailability.yaml data/taxa2gbiftypeavailability-cbd.yaml data/taxa2nativerangetypeavailability-cbd.yaml data/taxa2gbiftypeavailability-nagoya.yaml data/taxa2nativerangetypeavailability-nagoya.yaml

data_archive_zip:=$(shell basename $(CURDIR))-data.zip
downloads_archive_zip:=$(shell basename $(CURDIR))-downloads.zip

archive: data/taxa2gbiftypeavailability.yaml data/taxa2nativerangetypeavailability.yaml  data/taxa2gbiftypeavailability-cbd.yaml data/taxa2nativerangetypeavailability-cbd.yaml data/taxa2gbiftypeavailability-nagoya.yaml data/taxa2nativerangetypeavailability-nagoya.yaml
	mkdir -p archive	
	echo "Archived on $(date_formatted)" >> data/archive-info.txt
	zip archive/$(data_archive_zip) data/*.yaml -r
	echo "Archived on $(date_formatted)" >> downloads/archive-info.txt
	zip archive/$(downloads_archive_zip) downloads/* -r
	
clean:
	rm -rf data

sterilise:
	rm -rf data
	rm -rf downloads

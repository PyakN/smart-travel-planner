#!/bin/sh
# Cuts the areas in areas.txt out of their Geofabrik regions and merges them into one
# extract, areas.osm.pbf, in the current directory. Needs curl and osmium-tool.
set -eu

GEOFABRIK=${GEOFABRIK:-https://download.geofabrik.de}
mkdir -p regions parts

grep -v -e '^#' -e '^[[:space:]]*$' areas.txt | while read -r city region bbox; do
	name=$(echo "$region" | tr / -)
	echo "$city: $region ($bbox)"
	curl -fsSL --retry 3 -o "regions/$name.osm.pbf" "$GEOFABRIK/$region-latest.osm.pbf"
	osmium extract --bbox "$bbox" --set-bounds --overwrite \
		-o "parts/$city-$name.osm.pbf" "regions/$name.osm.pbf"
	# A region is ~100-450 MB; only its cut-out is kept.
	rm "regions/$name.osm.pbf"
done

osmium merge --overwrite -o areas.osm.pbf parts/*.osm.pbf
rm -r regions parts
osmium fileinfo areas.osm.pbf

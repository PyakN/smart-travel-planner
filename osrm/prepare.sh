#!/bin/sh
# Cuts the areas in areas.txt out of their Geofabrik regions and merges them into one
# extract, areas.osm.pbf, in the current directory. Needs curl and osmium-tool.
set -eu

GEOFABRIK=${GEOFABRIK:-https://download.geofabrik.de}
mkdir -p regions parts

grep -v -e '^#' -e '^[[:space:]]*$' areas.txt >areas.list

# Each region is downloaded once, even when several cities lie in it (Lisbon and Porto).
awk '{ print $2 }' areas.list | sort -u | while read -r region; do
	name=$(echo "$region" | tr / -)
	curl -fsSL --retry 3 -o "regions/$name.osm.pbf" "$GEOFABRIK/$region-latest.osm.pbf"
	awk -v region="$region" '$2 == region { print $1, $3 }' areas.list | while read -r city bbox; do
		echo "$city: $region ($bbox)"
		osmium extract --bbox "$bbox" --set-bounds --overwrite \
			-o "parts/$city-$name.osm.pbf" "regions/$name.osm.pbf"
	done
	# A region is ~20 MB-1 GB; only its cut-outs are kept.
	rm "regions/$name.osm.pbf"
done

osmium merge --overwrite -o areas.osm.pbf parts/*.osm.pbf
rm -r regions parts areas.list
osmium fileinfo areas.osm.pbf

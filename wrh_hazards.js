/**
 * Script: hazard.js
 * Description: Handles the NWS hazards GeoJson layer.
 * at WRH.
 *
 */


/**
 * Hazard variables
 */
var hazard;
var hazardHires = false;
var legendProducts = [];
var hazardOpacity = 0.8;
var hazardDisplayed = false;
var hazardType = "all";
var hazardBounds = [
    [25, -128],
    [49, -80]
];
var hazardQuery = false;
var hazardInterval;
var hazardUrl;
var hazardProducts = [];

/**
 * Category contents must match phenomenon property
 * from the hazard GeoJson file.
 */
var category = {
    "all": [
        "Flood", "Areal Flood", "Flash Flood",
        "Red Flag", "Fire Weather", "Fire", "Extreme Fire Danger",
        "Severe Thunderstorm", "Flash Flood", "Tornado",
        "Blizzard", "Snow", "Snow Squall", "Winter Storm", "Winter Weather", "Ice Storm", "Avalanche", "Lake Effect Snow", "Wind Chill","Cold Weather","Extreme Cold",
        "Lake Wind", "Marine", "Small Craft", "Hazardous Seas", "Gale", "Heavy Freezing Spray", "Hurrican Force Wind", "Storm",
        "Tsunami", "Coastal Flood", "High Surf", "Beach Hazards", 
        "Hurricane", "Tropical Storm", "Hurricane Winds",
        "Wind", "High Wind", "Fog", "Dense Fog", "Frost", "Hard Freeze", "Freeze", "Blowing Dust", "Dust", "Air Quality", "Extreme Heat", "Heat", "Excessive Heat", "Air Stagnation", "Brisk Wind", "Freezing Fog", "Severe Thunderstorm"
    ],
    "hydro": ["Flood", "Areal Flood", "Flash Flood"],
    "flash": ["Flash Flood"],
    "fire": ["Red Flag", "Fire Weather", "Fire", "Extreme Fire Danger"],
    "severe": ["Severe Thunderstorm", "Flash Flood", "Tornado"],
    "heat": ["Extreme Heat", "Heat","Excessive Heat"],
    "winter": ["Blizzard", "Snow", "Snow Squall", "Winter Storm", "Winter Weather", "Ice Storm", "Avalanche", "Lake Effect Snow", "Wind Chill"],
    "marine": ["Marine", "Small Craft", "Hazardous Seas", "Gale", "Heavy Freezing Spray", "Hurrican Force Wind","Storm"],
    "coastal": ["Tsunami", "Coastal Flood", "High Surf", "Beach Hazards"],
    "tropical": ["Hurricane", "Tropical Storm", "Hurricane Winds"],
    "npw": ["Wind", "High Wind", "Fog", "Dense Fog", "Frost", "Blowing Dust", "Dust", "Air Quality", "Extreme Heat", "Heat", "Excessive Heat", "Air Stagnation", "Brisk Wind", "Freezing Fog","Lake Wind","Cold Weather","Extreme Cold","Hard Freeze", "Freeze"]
};


/**
 * Toggle the hazard layer
 * 
 */
function toggleHazards() {

    // is the layer checked
    if ($('#hazard-enable').is(':checked')) {

        // show loading
        $("#load-div").show();

        // are we loading detailed hazards
        if (hazardHires) {

            // if layer already displayed...need to remove
            if (hazardDisplayed) { removeHazardLayer(); }

            // let folks know that not all products available with this layer
            $('#hazard-notice').show();

            // show update frequency
            $('#hazard-update-notice').show();

            // what type of hazards are we showing
            if (hazardType == "hi-all") {
                hazardUrl = "/gbh/WRhazards_reprojected.png?cachetime=" + Math.random();
            } else if (hazardType == "hi-hydro") {
                hazardUrl = "/gbh/hydrohazards_reprojected.png?cachetime=" + Math.random();
            } else if (hazardType == "hi-winter") {
                hazardUrl = "/gbh/winterhazards_reprojected.png?cachetime=" + Math.random();
            } else if (hazardType == "hi-npw") {
                hazardUrl = "/gbh/npwhazards_reprojected.png?cachetime=" + Math.random();
            } else if (hazardType == "hi-coastal") {
                hazardUrl = "/gbh/coastalhazards_reprojected.png?cachetime=" + Math.random();
            } else if (hazardType == "hi-marine") {
                hazardUrl = "/gbh/marinehazards_reprojected.png?cachetime=" + Math.random();
            } else if (hazardType == "hi-fire") {
                hazardUrl = "/gbh/firehazards_reprojected.png?cachetime=" + Math.random();
            }

            // add the image to the map
            hazard = L.imageOverlay(hazardUrl, hazardBounds, { opacity: hazardOpacity }).addTo(map).bringToFront();
            hazardDisplayed = true;

            // turn on hazard querying
            // whichMapClick("hazards", true);
            map.on("click", getCapInfo);

            // need to update legend 
            map.on("moveend", updateHazardLegend);
            updateHazardLegend()

            // update layer timestamp
            createHazardTimestamp(true);

            // show hazard legend
            viewHazardLegend(true);

            // need to keep layer refreshed
            hazardAutoupdate(true);

            // hide loading
            $("#load-div").hide();

        } else {

            // if layer already displayed...need to remove
            if (hazardDisplayed) { removeHazardLayer(); }

            // hide the hazard notice -- layer includes all products
            // $('#hazard-notice').hide();

            // NIDS - http://www.weather.gov/source/crh/allhazard.geojson
            $.ajax({
                type: 'GET',
                // url: "/data/allhazard.geojson",
                // url: "/map/json/WR_All_Hazards.json",
                url: "/source/wrh/hazards/json/WR_All_Hazards.json",
                dataType: 'json',
                success: function(json) {

                    // clear hazard legend for new products
                    $('#hazard-legend').empty();

                    // build table for hazard products
                    var tbl = "<table style='width:100%;'>\n";

                    // we have the hazard json file..time to parse
                    hazard = L.geoJson(json, {
                        /** Do we need to filter based on selected category */
                        filter: function(feature, layer) {
                            var prod_arr = feature.properties.PROD_TYPE.split(" ")
                            prod_arr.pop()
                            var chkval = prod_arr.join(" ")

                            // // Do not display Avalanche Warning until KSLC issue resolved - ck 12/23/2020
                            // var found_av = chkval.includes("Avalanche");
                            // if(found_av) { 
                            //     return false; 
                            // }

                            var inthere = $.inArray(chkval, category[hazardType]);
                            if (inthere > -1) {
                                if (hazardType != 'severe') {
                                    /** Check if this phenomenon is already added to legend */
                                    var indx = legendProducts.indexOf(chkval);
                                    if (indx == -1) {
                                        legendProducts[feature.properties.PROD_TYPE] = { "color": feature.properties.COLOR };
                                    }
                                    return true;
                                } else {
                                    if (feature.properties.SIG == "W") {
                                        /** Check if this phenomenon is already added to legend */
                                        var indx = legendProducts.indexOf(chkval);
                                        if (indx == -1) {
                                            legendProducts[feature.properties.PROD_TYPE] = { "color": feature.properties.COLOR };
                                        }
                                        return true;
                                    }
                                }
                            } else {
                                return false;
                            }
                        },
                        style: function(feature) {
                            return { color: feature.properties.COLOR, weight: 0.4, opacity: 1, fillOpacity: hazardOpacity };
                        }
                    }).addTo(map).bringToFront();
                    hazardDisplayed = true;

                    // generate legend
                    for (var key in legendProducts) {
                        var tmpkey = key;
                        if (key == "Fire Weather Warning") { tmpkey = "Red Flag Warning"; }
                        tbl += "<tr>";
                        tbl += "<td style='font-size:0.9em;'>" + tmpkey + "</td>";
                        tbl += "<td>&nbsp;</td>";
                        tbl += "<td style='background-color:" + legendProducts[key].color + ";border:1px solid black;width:20px;'></td>";
                        tbl += "</tr>";
                    }
                    tbl += "</table>";
                    $('#hazard-legend').html(tbl);

                    // update layer timestamp
                    createHazardTimestamp(true);

                    // turn on hazard querying
                    // whichMapClick("hazards",true);
                    map.on("click", getCapInfo);

                    // need to update legend 
                    // map.on("moveend", updateHazardLegend);
                    // updateHazardLegend();

                    // show hazard legend
                    viewHazardLegend(true);

                    // need to keep layer refreshed
                    hazardAutoupdate(true);

                    // hide loading
                    $("#load-div").hide();

                },
                error: function(x, stat, err) {
                    alert("There was a problem retrieving hazard information. Please try again later! \n\n Message: \n\n" + err);
			$("#load-div").hide();
                }
            });
        }

    } else {
        if (hazardDisplayed) { removeHazardLayer();
            $("#load-div").hide(); }
    }
}

/**
 * Remove the hazard layer from the map.
 */
function removeHazardLayer() {

    // is layer displayed
    if (hazardDisplayed) {

        // remove hazard layer and clean up
        map.removeLayer(hazard);
        map.closePopup();

        // reconfigure vars
        hazardDisplayed = false;
        legendProducts = [];

        // turn off hazard querying
        // whichMapClick("hazards",false);
        map.off("click", getCapInfo);

        // turn off legend updates
        map.off("moveend", updateHazardLegend);

        // update timestamp
        createHazardTimestamp(false);

        // hide the legend
        viewHazardLegend(false);

        // stop updating layer
        hazardAutoupdate(false);

    }
}

/**
 * Update the hazards layer if it is displayed
 */
function updateHazards() {
    if (hazardDisplayed) {

        // want to refresh layer
        toggleHazards();
    }
}

/**
 * Control the autoupdating of layer
 * 
 * @param {Boolean} bool Should be autoupdate layer
 */
function hazardAutoupdate(bool) {
    if (bool) {
        hazardInterval = setInterval(updateHazards, 300000);
        $("#hazard-refresh-notice").show();
    } else {
        clearInterval(hazardInterval);
        $("#hazard-refresh-notice").hide();
    }
}

/**
 * Change the desired hazard category
 *
 * @param {string} val Example: all, fire, hydrology, etc...
 */
function changeHazard(val) {
    hazardType = val;
    if (hazardType.substring(0, 2) == "hi") {
        hazardHires = true;
    } else {
        hazardHires = false;
    }
    if (hazardDisplayed) {

        // hazards are displayed so we need to refresh
        toggleHazards();
    }
}

/**
 * Change the geoHazard layer opacity
 *
 * @param {float} val Example: 0.0 = transparent, 1.0 = fully opaque
 */
function setHazardOpacity(val) {
    hazardOpacity = val / 100;
    if (hazardDisplayed) {
        if (hazardHires) {
            hazard.setOpacity(hazardOpacity);
        } else {
            hazard.setStyle({ fillOpacity: hazardOpacity });
        }
    }
}

/**
 * Make hazard update labels visible
 * 
 * @param {Boolean} bool
 */
function viewHazardLegend(bool) {
    if (bool) {
        $("#hazard-legend-body").show();
    } else {
        $("#hazard-legend").empty();
        $("#hazard-legend-body").hide();
    }
}

/**
 * Refresh hazard timestamp
 * 
 * @param {Boolean} bool
 */
function createHazardTimestamp(bool) {
    if (bool) {
        $('#hazard-timestamp').html("Updated: " + createTimestamp());
        $('#hazard-legend-timestamp').html("Updated: " + createTimestamp());
    } else {
        $('#hazard-timestamp').html("Layer Not Loaded");
        $('#hazard-legend-timestamp').html("Layer Not Loaded");
    }
}

/**
 * Capitalize the first letter in a word
 * 
 * @param {String} text
 * @returns {String}
 */
function capitalize(text) {
    var str = "";
    if (typeof text != 'undefined') {
        str = text.substring(0, 1).toUpperCase() + text.substring(1);

    }
    return str;
}

/**
 * Update legend for hires hazards based on hazard type
 * 
 */
function updateHazardLegend() {
    var hazLabels;
    var legend = $("#hazard-legend").get(0);
    legendProducts = [];
    var bbox = map.getBounds();
    var sw = bbox.getSouthWest();
    var ne = bbox.getNorthEast();
    var bboxstr = sw.lat + "," + sw.lng + "," + ne.lat + "," + ne.lng;

    $.ajax({
        type: "GET",
        url: 'php/getLegend.php?extents=' + bboxstr + "&type=" + hazardType,
        success: function(data) {
            eval(data);

            /** Create new table for the legend */
            $('#hazard-legend').empty();

            var tbl = document.createElement("table");
            tbl.setAttribute("width", "100%");
            var tblB = document.createElement("tbody");

            for (var k in hazLabels) {
                var row = document.createElement("tr");
                var cell = document.createElement("td");
                cell.style.padding = "0px";
                var txt = document.createTextNode(hazLabels[k].hazard);
                cell.appendChild(txt);
                cell.setAttribute("class", "bluefont");
                cell.setAttribute("align", "left");
                row.appendChild(cell);
                var cell = document.createElement("td");
                cell.setAttribute("align", "left");
                cell.setAttribute("height", "20px");
                cell.setAttribute("width", "20px");
                cell.style.padding = "0px";
                cell.style.backgroundColor = "#" + hazLabels[k].color;
                cell.style.border = "1px";
                cell.style.borderStyle = "solid";
                cell.style.borderColor = "black";
                row.appendChild(cell);
                tblB.appendChild(row);
            }
            tbl.appendChild(tblB);
            legend.appendChild(tbl);
            // $("#load-div").hide();
        },
        error: function(err) {
            console.log("Error retrieving legend information: " + err);
            // $("#load-div").hide();
        }
    });
}

/**
 * Retrieve NWS CAP alerts based on lat/lon point
 * 
 * NOTE: The lat/lon point is converted to zone and/or county to retrieve CAP XML, which
 * 		 can cause products to be approximate for hires images.
 * 
 * @param {L.latLng} point 
 */
function getCapInfo(point) {

    hazardProds = [];
    // show loading
    $("#load-div").show();

    $.ajax({
        type: "GET",
        url: "https://api.weather.gov/alerts?active=1&point=" + point.latlng.lat.toFixed(4) + "," + point.latlng.lng.toFixed(4),
        dataType: "json",
        success: function(json) {
            html = ""
        
            $.each(json.features, function(key, hazard) {
                var h = new Object;
                h.event = hazard.properties.event;
                h.headline = hazard.properties.headline;
                h.nws_headline = (hazard.properties.parameters.NWSheadline) ? hazard.properties.parameters.NWSheadline[0] : "N/A";
                if(hazard.properties.description.includes("'")) {
                    desc_str = hazard.properties.description;
                    h.description = desc_str.replace("'", "&apos;")
                } else {
                    h.description = (hazard.properties.description);
                }
                h.instruction = (hazard.properties.instruction) ? hazard.properties.instruction.replace(/'/g,"\"") : "N/A";
                h.effective = new Date(hazard.properties.effective); 
                h.expires = (hazard.properties.ends !== null) ? new Date(hazard.properties.ends) : "N/A"
                //if (h.expires > new Date('2023-01-31') & hazard.properties.senderName == "NWS Eureka CA") { return; }
                h.active = (h.expires != "N/A") ? (h.expires.getTime() - new Date().getTime()) / 60000 : "N/A";
                h.area = (hazard.properties.areaDesc) ? hazard.properties.areaDesc : "N/A";
                // h.diff_time = Math.round((h.expires.getTime() - new Date().getTime()) / 60000);
                // h.active = Math.round(h.diff_time / 60);
                h.vtec = hazard.properties.parameters.VTEC;
                // if (h.expires == new Date("2023-12-31T10:00:00-08:00")) { h.vtec = "xx" }
                if (h.active == "N/A") {
                    h.active_msg = "Active Until Further Notice";
                } else if (h.active >= 60) {
                    h.active_msg = "Active for next " + (h.active / 60).toFixed(1) + " hour(s)";
                } else if (h.active < 60 && h.active > 0) {
                    h.active_msg = "Active for next " + Math.round(h.active) + " minute(s)";
                } else {
                    h.active_msg = "Expired";
                }
                // h.active_type = "h";
                // if (h.active == 0) {
                //     h.active = Math.round(h.diff_time);
                //     h.active_type = "m";
                // } else if (h.active < 0) {
                //     h.active_type = "e";
                // }
                if (!containsHazard(h)) { hazardProds.push(h); }
            });

            if(hazardProds.length > 0) {

                for (var j in hazardProds) {
                    html += "<div class='container' style='max-width:375px;margin-top:5px;'>";
                    html += "	<div class='row'>";
                    html += "		<div class='col-xs-6' style='padding:0px;'>";
                    // html += '			<font style="font-weight:bold;font-size:1.1em;text-decoration:underline;"><a href="#">' + hazardProds[j].event + '</a></font>';
                    var test = JSON.stringify(hazardProds[j]);
                    html += "			<font style='font-weight:bold;font-size:1.1em;text-decoration:underline;'><a href='#' onclick='javascript:showHazardMessage(" + JSON.stringify(hazardProds[j]) + ");' >" + hazardProds[j].event + "</a></font>";
                    html += "		</div>";
                    html += "		<div class='col-xs-6' style='padding:0px;text-align:right;'>";
                    html += "			<font style='color:#999;'>" + hazardProds[j].active_msg + "</font>";
                    html += "		</div>";
                    html += "	</div>";
                    html += "	<div class='row'>";
                    html += "		<div class='col-xs-12' style='padding:0px;'>";
                    html += "			<font style='font-size:1.0em;'><b>Effective: </b>" + dateFormat(hazardProds[j].effective, "ddd mmm d, yyyy h:MM TT Z") + "</font>";
                    html += "		</div>";
                    html += "	</div>";

                    html += "	<div class='row' style='background-color:rgb(245,245,245);padding:2px;margin-top:3px;border:1px solid #33334d;max-width:375px;'>";
                    if (hazardProds[j].nws_headline != "N/A") {
                        html += "					<font style='font-size:1.0em;'>" + hazardProds[j].nws_headline.trim();
                    } else {
                        html += "					<font style='font-size:1.0em;'>" + hazardProds[j].headline.trim();
                    }
                    // if (hazardProds[j].headline.length > 1) {
                    //     html += "					<font style='font-size:1.0em;'>" + hazardProds[j].headline[1].trim();
                    // } else {
                    //     html += "					<font style='font-size:1.0em;'>" + hazardProds[j].headline[0].trim();
                    // }
                    html += "	</div>";
                    html += "</div>";
                }

                new L.responsivePopup({ autoPanPadding: [10,10], maxHeight: 500, maxWidth: 500, closeButton: true, autoPan: true }).setContent(html).setLatLng(point.latlng).openOn(map);
                // hide loading
                $("#load-div").hide();

            } else {
                html += "There are no active watches, warnings<br>or advisories for this point.";
                new L.responsivePopup({ autoPanPadding: [10,10], maxHeight: 500, maxWidth: 500, closeButton: true, autoPan: true }).setContent(html).setLatLng(point.latlng).openOn(map);
                $("#load-div").hide();
            }

        },
        error: function(err) {
            console.log("Error retrieving zone CAP products: " + err);
            $("#load-div").hide();
        },
        complete: function() {
            $("#load-div").hide();
        }
    });

    // $.ajax({
    //     type: "GET",
    //     url: "https://api.weather.gov/points/" + point.latlng.lat.toFixed(2) + "," + point.latlng.lng.toFixed(2),
    //     dataType: "json",
    //     success: function(json) {
    //         var pzonePath = (json.properties.forecastZone) ? json.properties.forecastZone.split("/") : [];
    //         var fzonePath = (json.properties.fireWeatherZone) ? json.properties.fireWeatherZone.split("/") : [];
    //         // var czonePath = (json.properties.county) ? json.properties.county.split("/") : [];
    //         var pzone = (pzonePath.length > 0) ? pzonePath[pzonePath.length - 1] : "";
    //         var fzone = (fzonePath.length > 0) ? fzonePath[fzonePath.length - 1] : "";
    //         // var czone = (czonePath.length > 0) ? czonePath[czonePath.length-1] : "";
    //         var html = "";

    //         $.ajax({
    //             type: "GET",
    //             url: "https://alerts.weather.gov/cap/wwaatmget.php?x=" + pzone,
    //             dataType: "xml",
    //             success: function(xml) {
    //                 var ent = $(xml).find("entry").each(function() {
    //                     var html = "";
    //                     var title = $(this).find("title").text();
    //                     if (title != "There are no active watches, warnings or advisories") {
    //                         var h = new Object;
    //                         h.link = $(this).find("link").attr("href");
    //                         h.linkarr = h.link.split("x=");
    //                         h.summary = $(this).find('summary').text().split("...");
    //                         h.event = $(this).find("cap\\:event").text();
    //                         h.eff = new Date($(this).find("cap\\:effective, effective").text());
    //                         h.exp = new Date($(this).find("cap\\:expires, expires").text());
    //                         h.difft = Math.round((h.exp.getTime() - new Date().getTime()) / 60000);
    //                         h.active = Math.round(h.difft / 60);
    //                         h.active_type = "h";
    //                         if (h.active == 0) {
    //                             h.active = Math.round(h.difft);
    //                             h.active_type = "m";
    //                         } else if (h.active < 0) {
    //                             h.active_type = "e";
    //                         }
    //                         if (!containsHazard(h)) { hazardProds.push(h); }
    //                     }
    //                 });
    //             },
    //             error: function(err) {
    //                 console.log("Error retrieving zone CAP products: " + err);
    //             },
    //             complete: function() {
    //                 if (fzone) {
    //                     $.ajax({
    //                         type: "GET",
    //                         url: "https://alerts.weather.gov/cap/wwaatmget.php?x=" + fzone,
    //                         dataType: "xml",
    //                         success: function(xml) {
    //                             var ent = $(xml).find("entry").each(function() {
    //                                 var html = "";
    //                                 var title = $(this).find("title").text();
    //                                 if (title != "There are no active watches, warnings or advisories") {
    //                                     var h = new Object;
    //                                     h.link = $(this).find("link").attr("href");
    //                                     h.linkarr = h.link.split("x=");
    //                                     h.summary = $(this).find('summary').text().split("...");
    //                                     h.event = $(this).find("cap\\:event").text();
    //                                     h.eff = new Date($(this).find("cap\\:effective, effective").text());
    //                                     h.exp = new Date($(this).find("cap\\:expires, expires").text());
    //                                     h.difft = Math.round((h.exp.getTime() - new Date().getTime()) / 60000);
    //                                     h.active = Math.round(h.difft / 60);
    //                                     h.active_type = "h";
    //                                     if (h.active == 0) {
    //                                         h.active = Math.round(h.difft);
    //                                         h.active_type = "m";
    //                                     } else if (h.active < 0) {
    //                                         h.active_type = "e";
    //                                     }
    //                                     if (!containsHazard(h)) { hazardProds.push(h); }
    //                                 }

    //                                 if (hazardProds.length > 0) {
    //                                     for (var j in hazardProds) {
    //                                         html += "<div style='margin-top:5px;'>";
    //                                         html += "	<div class='row'>";
    //                                         html += "		<div class='col-xs-6' style='padding:0px;'>";
    //                                         html += '			<font style="font-weight:bold;font-size:1.1em;text-decoration:underline;"><a href="#" onclick="javascript:showHazardCapMessage(\'' + hazardProds[j].event + '\',\'' + hazardProds[j].linkarr[1] + '\');" >' + hazardProds[j].event + '</a></font>';
    //                                         html += "		</div>";
    //                                         html += "		<div class='col-xs-6' style='padding:0px;text-align:right !important;'>";
    //                                         if (hazardProds[j].active_type == "h") {
    //                                             html += "			<font style='color:#999;'>Active for next " + hazardProds[j].active + " hour(s)</font>";
    //                                         } else if (hazardProds[j].active_type == "m") {
    //                                             html += "			<font style='color:#999;'>Active for next " + hazardProds[j].active + " minute(s)</font>";
    //                                         } else {
    //                                             html += "			<font style='color:#999;'>Expired</font>";
    //                                         }
    //                                         html += "		</div>";
    //                                         html += "	</div>";
    //                                         html += "	<div class='row'>";
    //                                         html += "		<div class='col-xs-12' style='padding:0px;'>";
    //                                         html += "			<font style='font-size:1.0em;'><b>Effective: </b>" + dateFormat(hazardProds[j].eff, "ddd mmm d, yyyy h:MM TT Z") + "</font>";
    //                                         html += "		</div>";
    //                                         html += "	</div>";

    //                                         html += "	<div class='row' style='background-color:rgb(245,245,245);padding:2px;margin-top:3px;border:1px solid #33334d;max-width:375px;'>";
    //                                         if (hazardProds[j].summary.length > 1) {
    //                                             html += "					<font style='font-size:1.0em;'>" + hazardProds[j].summary[1].trim();
    //                                         } else {
    //                                             html += "					<font style='font-size:1.0em;'>" + hazardProds[j].summary[0].trim();
    //                                         }
    //                                         html += "	</div>";
    //                                         html += "</div>";
    //                                         new L.responsivePopup({ autoPanPadding: [10,10], maxHeight: 500, maxWidth: 500, closeButton: true, autoPan: true }).setContent(html).setLatLng(point.latlng).openOn(map);
    //                                         $("#load-div").hide();
    //                                     }
    //                                 } else {
    //                                     html += "There are no active watches, warnings<br>or advisories for this point.";
    //                                     new L.responsivePopup({ autoPanPadding: [10,10], maxHeight: 500, maxWidth: 500, closeButton: true, autoPan: true }).setContent(html).setLatLng(point.latlng).openOn(map);
    //                                     $("#load-div").hide();
    //                                 }
    //                             });
    //                         },
    //                         error: function(err) {
    //                             console.log("Error retrieving county CAP products: " + err);
    //                         }
    //                     });
    //                 } else {
    //                     if (hazardProds.length > 0) {
    //                         for (var j in hazardProds) {
    //                             html += "<div class='container' style='max-width:375px;margin-top:5px;'>";
    //                             html += "	<div class='row'>";
    //                             html += "		<div class='col-xs-6' style='padding:0px;'>";
    //                             html += '			<font style="font-weight:bold;font-size:1.1em;text-decoration:underline;"><a href="#" onclick="javascript:showHazardCapMessage(\'' + hazardProds[j].event + '\',\'' + hazardProds[j].linkarr[1] + '\');" >' + hazardProds[j].event + '</a></font>';
    //                             html += "		</div>";
    //                             html += "		<div class='col-xs-6' style='padding:0px;text-align:right;'>";
    //                             if (hazardProds[j].active_type == "h") {
    //                                 html += "			<font style='color:#999;'>Active for next " + hazardProds[j].active + " hour(s)</font>";
    //                             } else if (hazardProds[j].active_type == "m") {
    //                                 html += "			<font style='color:#999;'>Active for next " + hazardProds[j].active + " minute(s)</font>";
    //                             } else {
    //                                 html += "			<font style='color:#999;'>Expired</font>";
    //                             }
    //                             html += "		</div>";
    //                             html += "	</div>";
    //                             html += "	<div class='row'>";
    //                             html += "		<div class='col-xs-12' style='padding:0px;'>";
    //                             html += "			<font style='font-size:1.0em;'><b>Effective: </b>" + dateFormat(hazardProds[j].eff, "ddd mmm d, yyyy h:MM TT Z") + "</font>";
    //                             html += "		</div>";
    //                             html += "	</div>";

    //                             html += "	<div class='row' style='background-color:rgb(245,245,245);padding:2px;margin-top:3px;border:1px solid #33334d;max-width:375px;'>";
    //                             if (hazardProds[j].summary.length > 1) {
    //                                 html += "					<font style='font-size:1.0em;'>" + hazardProds[j].summary[1].trim();
    //                             } else {
    //                                 html += "					<font style='font-size:1.0em;'>" + hazardProds[j].summary[0].trim();
    //                             }
    //                             html += "	</div>";
    //                             html += "</div>";
    //                             new L.responsivePopup({ autoPanPadding: [10,10], maxHeight: 500, maxWidth: 500, closeButton: true, autoPan: true }).setContent(html).setLatLng(point.latlng).openOn(map);
    //                             // hide loading
    //                             $("#load-div").hide();
    //                         }
    //                     } else {
    //                         html += "There are no active watches, warnings<br>or advisories for this point.";
    //                         new L.responsivePopup({ autoPanPadding: [10,10], maxHeight: 500, maxWidth: 500, closeButton: true, autoPan: true }).setContent(html).setLatLng(point.latlng).openOn(map);
    //                         // hide loading
    //                         $("#load-div").hide();
    //                     }
    //                 }
    //             }
    //         });

    //     },
    //     complete: function() {
    //         // hide loading
    //         $("#load-div").hide();
    //     },
    //     error: function(err) {
    //             // hide loading
    //             $("#load-div").hide();
    //         } //close success
    // }); //close .ajax

}

/**
 * Does the displayed products contain a specific hazard
 * 
 * @param {Object} obj 
 */
function containsHazard(obj) {
    var found = false;
    for (var m in hazardProds) {
        for (var v in hazardProds[m].vtec) {
            var searchVTEC = hazardProds[m].vtec[v];
            for (var o in obj.vtec) {
                if (obj.vtec[o] == searchVTEC) {
                    found = true;
                }
            }
            // if ($.inArray(searchVTEC,obj.vtec)) {
            //     found = true;
            // }
        }
        // if (hazardProds[m].vtec == obj.vtec) {
        //     found = true;
        // }
    }
    return found;
    // var found = false;
    // for (var m in hazardProds) {
    //     if (hazardProds[m].event == obj.event) {
    //         found = true;
    //     }
    // }
    // return found;
}

/**
 * Should we show the loading indicator
 * 
 * @param {Boolean} bool 
 */
function showHazardLoading(bool) {
    if (bool) {
        $("#hazard-loading").show();
    } else {
        $("#hazard-loading").hide();
    }

}

/**
 * Show a modal window with CAP message displayed
 * 
 * @param {Object} h  hazard info object
 */
function showHazardMessage(h) {
    $("#hazard-content").empty();
    $("#hazard-title").html(h.event);

    var hazardHtml = "";
    hazardHtml += "<div style='margin:0px 5px;'>";
    hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
    hazardHtml += "			<div class='col-xs-12' style='padding:0px;'>";
    hazardHtml += "				<font style='color:#4b9cd7;'>Description:</font>";
    hazardHtml += "			</div>";
    hazardHtml += "		</div>";
    hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
    hazardHtml += "			<div class='col-xs-12' style='padding:0px;overflow:auto;'>";
    hazardHtml += "				<pre>" + h.description.replace(/\r\n|\n|\r/gm, '<br />') + "</pre>";
    hazardHtml += "			</div>";
    hazardHtml += "		</div>";
    hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
    hazardHtml += "			<div class='col-xs-12' style='padding:0px;'>";
    hazardHtml += "				<br><font style='color:#4b9cd7;'>Instructions:</font>";
    hazardHtml += "			</div>";
    hazardHtml += "		</div>";
    hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
    hazardHtml += "			<div class='col-xs-12' style='padding:0px;overflow:auto;'>";
    hazardHtml += "				<pre>" + h.instruction + "</pre>";
    hazardHtml += "			</div>";
    hazardHtml += "		</div>";
    hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
    hazardHtml += "			<div class='col-xs-12' style='padding:0px;'>";
    hazardHtml += "				<br><font style='color:#4b9cd7;'>Affected Area(s):</font>";
    hazardHtml += "			</div>";
    hazardHtml += "		</div>";
    hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
    hazardHtml += "			<div class='col-xs-12' style='padding:0px;overflow:auto;'>";
    hazardHtml += "				<div style='font-family:Consolas,monospace;background:rgb(245,245,245);border:1px solid rgb(204,204,204);padding:5px;'>" + h.area + "</div>";
    hazardHtml += "			</div>";
    hazardHtml += "		</div>";
    hazardHtml += "</div>"

    // alert(html);
    $("#hazard-content").html(hazardHtml);
    $("#hazard-dialog").modal('show');
}
// function showHazardCapMessage(product, url) {
//     $.ajax({
//         type: "GET",
//         url: "https://alerts.weather.gov/cap/wwacapget.php",
//         data: { x: url },
//         dataType: "xml",
//         success: function(xml) {

//             $("#hazard-content").empty();

//             // parse CAP message
//             var event = $(xml).find("event").text();
//             var description = '<pre>' + $(xml).find("description").text() + '</pre>';
//             var instructions = '<pre>' + $(xml).find("instruction").text() + '</pre>';
//             var area = '<div style="font-family:Consolas,monospace;background:rgb(245,245,245);border:1px solid rgb(204,204,204);padding:5px;">' + $(xml).find("areaDesc").text();

//             $("#hazard-title").html(product);

//             var hazardHtml = "";
//             hazardHtml += "<div style='margin:0px 5px;'>";
//             hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
//             hazardHtml += "			<div class='col-xs-12' style='padding:0px;'>";
//             hazardHtml += "				<font style='color:#4b9cd7;'>Description:</font>";
//             hazardHtml += "			</div>";
//             hazardHtml += "		</div>";
//             hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
//             hazardHtml += "			<div class='col-xs-12' style='padding:0px;overflow:auto;'>";
//             hazardHtml += "				" + description;
//             hazardHtml += "			</div>";
//             hazardHtml += "		</div>";
//             hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
//             hazardHtml += "			<div class='col-xs-12' style='padding:0px;'>";
//             hazardHtml += "				<br><font style='color:#4b9cd7;'>Instructions:</font>";
//             hazardHtml += "			</div>";
//             hazardHtml += "		</div>";
//             hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
//             hazardHtml += "			<div class='col-xs-12' style='padding:0px;overflow:auto;'>";
//             hazardHtml += "				" + instructions;
//             hazardHtml += "			</div>";
//             hazardHtml += "		</div>";
//             hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
//             hazardHtml += "			<div class='col-xs-12' style='padding:0px;'>";
//             hazardHtml += "				<br><font style='color:#4b9cd7;'>Affected Area(s):</font>";
//             hazardHtml += "			</div>";
//             hazardHtml += "		</div>";
//             hazardHtml += "		<div class='row' style='font-size:0.9em;'>";
//             hazardHtml += "			<div class='col-xs-12' style='padding:0px;overflow:auto;'>";
//             hazardHtml += "				" + area;
//             hazardHtml += "			</div>";
//             hazardHtml += "		</div>";
//             hazardHtml += "</div>"

//             // alert(html);
//             $("#hazard-content").html(hazardHtml);
//             $("#hazard-dialog").modal('show');
//         }
//     });
// }


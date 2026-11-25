// Cameroon outline for the venue map, as [lon, lat] points (clockwise from the Nigeria border at the coast).
// Hand-traced and approximate (about 0.1-0.2 degrees): it is a backdrop for the venue dots, not a boundary.
export const CAMEROON = [
  [8.50, 4.55], [8.80, 5.15], [8.85, 5.80], [9.40, 6.30], [9.80, 6.80], [10.20, 7.05], [10.60, 7.00],
  [11.10, 6.45], [11.60, 6.90], [11.85, 7.10], [12.05, 7.60], [12.25, 8.40], [12.80, 8.75], [13.00, 9.30],
  [13.25, 9.95], [13.60, 10.20], [13.75, 10.95], [14.10, 11.25], [14.45, 11.55], [14.60, 12.20],
  [14.20, 12.40], [14.10, 13.05], [14.50, 12.85], [14.90, 12.15], [15.05, 11.40], [15.10, 10.70],
  [15.50, 10.25], [15.05, 10.05], [14.20, 9.95], [13.95, 9.60], [14.30, 9.00], [15.10, 8.30],
  [15.50, 7.55], [14.80, 6.70], [14.75, 6.25], [14.55, 5.30], [14.60, 4.60], [15.10, 4.00],
  [15.30, 3.30], [16.10, 2.70], [16.20, 2.20], [16.07, 1.65], [15.25, 2.00], [14.50, 2.15],
  [13.30, 2.16], [12.50, 2.20], [11.35, 2.25], [9.80, 2.35], [9.85, 3.00], [9.65, 3.55],
  [9.45, 3.90], [9.00, 4.00], [8.85, 4.30],
];

// Map frame (lon 8.3-16.3, lat 1.5-13.2) drawn into a 400 x 560 viewBox; 1 degree of lat ~ 1 degree of lon here.
export const VIEW = { w: 400, h: 560 };
export function project(lat, lon) {
  const x = ((lon - 8.3) / (16.3 - 8.3)) * 380 + 10;
  const y = ((13.2 - lat) / (13.2 - 1.5)) * 540 + 10;
  return [x, y];
}

export function outlinePath() {
  return CAMEROON.map(([lon, lat], i) => {
    const [x, y] = project(lat, lon);
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + " Z";
}

declare module "leaflet.heat";
declare module "leaflet" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function heatLayer(latlngs: Array<[number, number, number?]>, options?: any): Layer;
}
export {};

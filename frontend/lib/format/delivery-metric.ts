/** The unit a channel counts its delivery in, as the API names it. */
export type DeliveryMetric = "impressions" | "ots";

const LABEL: Record<DeliveryMetric, string> = { impressions: "impresiones", ots: "OTS" };

/** The unit as shown on screen: «impresiones» or «OTS». */
export function metricLabel(metric: DeliveryMetric): string {
  return LABEL[metric];
}

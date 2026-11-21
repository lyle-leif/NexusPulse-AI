import PageSkeleton from "./components/Skeleton";

export default function Loading() {
  return <PageSkeleton label="Loading store metrics. The first load computes them from the database, including each channel, device and category, and can take about a minute." />;
}

import PageSkeleton from "./components/Skeleton";

export default function Loading() {
  return <PageSkeleton label="Loading store metrics. The first load computes them from the database and can take about 15 seconds." />;
}

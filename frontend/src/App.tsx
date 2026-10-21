import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { EmptyNote } from "./components/StateViews";
import OverviewPage from "./pages/OverviewPage";
import ExplorePage from "./pages/ExplorePage";
import RestaurantPage from "./pages/RestaurantPage";
import PopularPage from "./pages/PopularPage";
import HiddenGemsPage from "./pages/HiddenGemsPage";
import NewlyDiscoveredPage from "./pages/NewlyDiscoveredPage";
import ComparePage from "./pages/ComparePage";
import AnalyticsPage from "./pages/AnalyticsPage";
import MethodologyPage from "./pages/MethodologyPage";

function NotFound() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16">
      <EmptyNote title="Page not found"><Link className="font-semibold text-leaf underline" to="/">Back to the overview</Link></EmptyNote>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="explore" element={<ExplorePage />} />
        <Route path="restaurants/:id" element={<RestaurantPage />} />
        <Route path="popular" element={<PopularPage />} />
        <Route path="hidden-gems" element={<HiddenGemsPage />} />
        <Route path="new" element={<NewlyDiscoveredPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="methodology" element={<MethodologyPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

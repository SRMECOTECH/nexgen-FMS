import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import Spinner from './components/ui/Spinner';

const Dashboard      = lazy(() => import('./pages/Dashboard'));
const LiveMap        = lazy(() => import('./pages/LiveMap'));
const Monitoring     = lazy(() => import('./pages/Monitoring'));

const Trips          = lazy(() => import('./pages/Trips'));
const Vehicles       = lazy(() => import('./pages/Vehicles'));
const Drivers        = lazy(() => import('./pages/Drivers'));
const Alerts         = lazy(() => import('./pages/Alerts'));
const Geofences      = lazy(() => import('./pages/Geofences'));

const MLHub          = lazy(() => import('./pages/MLHub'));
const Pipelines      = lazy(() => import('./pages/Pipelines'));
const ModelRegistry  = lazy(() => import('./pages/ModelRegistry'));

const DataCatalog    = lazy(() => import('./pages/DataCatalog'));
const DataBrowser    = lazy(() => import('./pages/DataBrowser'));
const SchemaDesigner = lazy(() => import('./pages/SchemaDesigner'));
const DataQuality    = lazy(() => import('./pages/DataQuality'));
const Connectors     = lazy(() => import('./pages/Connectors'));
const IoTDevices     = lazy(() => import('./pages/IoTDevices'));

const BehavioralPatterns = lazy(() => import('./pages/BehavioralPatterns'));
const Partners           = lazy(() => import('./pages/Partners'));
const Lanes              = lazy(() => import('./pages/Lanes'));
const GpsFeed            = lazy(() => import('./pages/GpsFeed'));
const HaltsRests         = lazy(() => import('./pages/HaltsRests'));
const JourneyDetail      = lazy(() => import('./pages/JourneyDetail'));
const VehicleDetail      = lazy(() => import('./pages/VehicleDetail'));

const RouteIntelligence         = lazy(() => import('./pages/RouteIntelligence'));
const RouteIntelligenceUpload   = lazy(() => import('./pages/RouteIntelligenceUpload'));
const RouteIntelligenceTrip     = lazy(() => import('./pages/RouteIntelligenceTrip'));
const RouteIntelligenceCompare  = lazy(() => import('./pages/RouteIntelligenceCompare'));
const RouteIntelligenceInsights = lazy(() => import('./pages/RouteIntelligenceInsights'));

const Diagnostics    = lazy(() => import('./pages/Diagnostics'));
const Logs           = lazy(() => import('./pages/Logs'));
const Recovery       = lazy(() => import('./pages/Recovery'));
const Configuration  = lazy(() => import('./pages/Configuration'));

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-0)', color: 'var(--fg-1)' }}>
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">
            <Suspense fallback={<Spinner />}>
              <Routes>
                {/* Overview */}
                <Route path="/"            element={<Dashboard />} />
                <Route path="/map"         element={<LiveMap />} />
                <Route path="/monitoring"  element={<Monitoring />} />

                {/* Operations */}
                <Route path="/trips"       element={<Trips />} />
                <Route path="/partners"    element={<Partners />} />
                <Route path="/vehicles"    element={<Vehicles />} />
                <Route path="/drivers"     element={<Drivers />} />
                <Route path="/alerts"      element={<Alerts />} />
                <Route path="/geofences"   element={<Geofences />} />

                {/* Intelligence */}
                <Route path="/ml"           element={<MLHub />} />
                <Route path="/ml/pipelines" element={<Pipelines />} />
                <Route path="/ml/models"    element={<ModelRegistry />} />

                {/* Data */}
                <Route path="/data/catalog"    element={<DataCatalog />} />
                <Route path="/data/browser"    element={<DataBrowser />} />
                <Route path="/data/schema"     element={<SchemaDesigner />} />
                <Route path="/data/quality"    element={<DataQuality />} />
                <Route path="/data/connectors" element={<Connectors />} />
                <Route path="/data/devices"    element={<IoTDevices />} />

                {/* Analytics (real-data driven) */}
                <Route path="/gps"                 element={<GpsFeed />} />
                <Route path="/gps/:vehicle"        element={<VehicleDetail />} />
                <Route path="/halts"               element={<HaltsRests />} />
                <Route path="/halts/:vehicle/:trip" element={<JourneyDetail />} />
                <Route path="/analytics/behaviour" element={<BehavioralPatterns />} />
                <Route path="/analytics/lanes"     element={<Lanes />} />

                {/* Route Intelligence — upload-driven deep analysis */}
                <Route path="/route-intel"                       element={<RouteIntelligence />} />
                <Route path="/route-intel/uploads/:uploadId"     element={<RouteIntelligenceUpload />} />
                <Route path="/route-intel/trips/:tripId"         element={<RouteIntelligenceTrip />} />
                <Route path="/route-intel/compare/:cmpId"        element={<RouteIntelligenceCompare />} />
                <Route path="/route-intel/insights"              element={<RouteIntelligenceInsights />} />

                {/* System */}
                <Route path="/system/diagnostics" element={<Diagnostics />} />
                <Route path="/system/logs"        element={<Logs />} />
                <Route path="/system/recovery"    element={<Recovery />} />
                <Route path="/system/config"      element={<Configuration />} />
              </Routes>
            </Suspense>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}

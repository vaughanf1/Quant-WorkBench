import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Screener from "@/pages/Screener";
import Backtest from "@/pages/Backtest";
import Monitor from "@/pages/Monitor";
import Data from "@/pages/Data";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/screener" element={<Screener />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/monitor" element={<Monitor />} />
        <Route path="/data" element={<Data />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

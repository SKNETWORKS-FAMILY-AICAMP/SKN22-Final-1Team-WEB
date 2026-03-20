import { createBrowserRouter } from "react-router-dom";
import { SplashPage } from "@/pages/SplashPage";
import { ServiceStartPage } from "@/pages/ServiceStartPage";
import { NewCustomerPage } from "@/pages/NewCustomerPage";
import { ExistingCustomerPage } from "@/pages/ExistingCustomerPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { SurveyPage } from "@/pages/SurveyPage";
import { RecommendationPage } from "@/pages/RecommendationPage";
import { AdminPage } from "@/pages/AdminPage";

export const router = createBrowserRouter(
  [
    { path: "/", element: <SplashPage /> },
    { path: "/index.html", element: <SplashPage /> },
    { path: "/service", element: <ServiceStartPage /> },
    { path: "/register", element: <NewCustomerPage /> },
    { path: "/existing", element: <ExistingCustomerPage /> },
    { path: "/dashboard", element: <DashboardPage /> },
    { path: "/survey", element: <SurveyPage /> },
    { path: "/recommendation", element: <RecommendationPage /> },
    { path: "/admin", element: <AdminPage /> },
    { path: "*", element: <SplashPage /> }
  ],
  {
    basename: "/customer"
  }
);

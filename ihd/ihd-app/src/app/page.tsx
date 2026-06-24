import DashboardShell from "@/components/DashboardShell";
import EventsWidget from "@/components/home/EventsWidget";
import FoodWidget from "@/components/home/FoodWidget";
import TripWidget from "@/components/home/TripWidget";
import KidsWidget from "@/components/home/KidsWidget";
import EnergyWidget from "@/components/home/EnergyWidget";
import SensorWidget from "@/components/home/SensorWidget";
import HadleyWidget from "@/components/home/HadleyWidget";
import PetWidget from "@/components/home/PetWidget";

export default function HomePage() {
  return (
    <DashboardShell>
      <div
        className="grid gap-3 pt-3 h-full"
        style={{
          gridTemplateColumns: "1fr 1fr 1fr",
          gridTemplateRows: "1fr 1fr",
        }}
      >
        {/* Col 1: events top, kids bottom */}
        <div className="flex flex-col gap-3 row-span-2">
          <EventsWidget />
          <KidsWidget />
        </div>
        {/* Col 2, Row 1 */}
        <FoodWidget />
        {/* Col 3, Row 1 */}
        <TripWidget />
        {/* Col 2, Row 2: three stacked mini-cards */}
        <div className="flex flex-col gap-2">
          <EnergyWidget />
          <SensorWidget />
          <HadleyWidget />
        </div>
        {/* Col 3, Row 2 */}
        <PetWidget />
      </div>
    </DashboardShell>
  );
}

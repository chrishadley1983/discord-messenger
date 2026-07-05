import DashboardShell from "@/components/DashboardShell";
import EventsWidget from "@/components/home/EventsWidget";
import FoodWidget from "@/components/home/FoodWidget";
import CountdownWidget from "@/components/home/CountdownWidget";
import KidsWidget from "@/components/home/KidsWidget";
import EnergyWidget from "@/components/home/EnergyWidget";
import SensorWidget from "@/components/home/SensorWidget";
import HadleyWidget from "@/components/home/HadleyWidget";
import PetWidget from "@/components/home/PetWidget";

export default function HomePage() {
  return (
    <DashboardShell>
      <div
        className="grid gap-3 h-full stagger-in"
        style={{
          gridTemplateColumns: "1fr 1fr 1fr",
          gridTemplateRows: "1fr 1fr",
        }}
      >
        {/* Col 1: events top, kids bottom */}
        <div className="flex flex-col gap-3 row-span-2 min-h-0">
          <EventsWidget />
          <KidsWidget />
        </div>
        {/* Col 2, Row 1 */}
        <FoodWidget />
        {/* Col 3, Row 1: countdowns + compact business strip */}
        <div className="flex flex-col gap-3 min-h-0">
          <div className="flex-1 min-h-0 flex flex-col [&>*]:flex-1 [&>*]:min-h-0 [&>*]:overflow-hidden">
            <CountdownWidget />
          </div>
          <HadleyWidget />
        </div>
        {/* Col 2, Row 2: energy + sensors */}
        <div className="flex flex-col gap-3 min-h-0">
          <div className="flex-1 min-h-0 flex flex-col [&>*]:flex-1 [&>*]:min-h-0 [&>*]:overflow-hidden">
            <EnergyWidget />
          </div>
          <div className="flex-1 min-h-0 flex flex-col [&>*]:flex-1 [&>*]:min-h-0 [&>*]:overflow-hidden">
            <SensorWidget />
          </div>
        </div>
        {/* Col 3, Row 2 */}
        <PetWidget />
      </div>
    </DashboardShell>
  );
}

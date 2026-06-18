import { useState } from "react";
import type { GameConnection } from "../useGameSocket";
import { Chat } from "./Chat";
import { MissionList } from "./MissionList";
import { Facilities } from "./Facilities";

interface Props {
  conn: GameConnection;
  onOpenFacility: (id: string) => void;
}

export function CommandCenter({ conn, onOpenFacility }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const st = conn.state;

  return (
    <div className="cc-body">
      <Chat
        messages={conn.chat}
        online={st?.playersOnline ?? 0}
        onSend={conn.sendChat}
      />
      <MissionList
        missions={st?.missions ?? []}
        critical={st?.criticalCount ?? 0}
        selected={selected}
        onSelect={(name) => {
          setSelected(name);
          onOpenFacility(`MISSION:${name}`);
        }}
      />
      <Facilities onOpen={onOpenFacility} />
    </div>
  );
}

import { useRef } from "react";

const positions = [
    ["1", "Carry", "M12 4v16M4 12h16M12 8l4 4-4 4-4-4z"],
    ["2", "Mid", "M4 20 20 4M13 4h7v7M4 13v7h7"],
    ["3", "Offlane", "M5 4h14v7c0 5-3.5 8-7 10-3.5-2-7-5-7-10zM9 12l2 2 4-4"],
    ["4", "Soft Support", "M5 14l3 3 3-6 3 3 5-7M14 7h5v5"],
    ["5", "Hard Support", "M12 3v18M3 12h18M6 6l12 12M18 6 6 18"],
];

const ranks = ["Unranked", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"];

function FilterIcon({ option }) {
    if (option.medal) {
        return <img className="rec-filter-icon" src={"/ranks/rank_icon_" + option.medal + ".png"} width="25" height="25" alt="" />;
    }
    return (
        <svg className="rec-filter-icon" width="25" height="25" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d={option.path || "M12 3l7 5v7l-7 6-7-6V8zM9 12l2 2 4-4"} />
        </svg>
    );
}

function RecommendationFilter({ label, value, options, onChange }) {
    const disclosure = useRef(null);
    const trigger = useRef(null);
    const selected = options.find((option) => option.id === value) ?? options[0];

    function close(restoreFocus) {
        disclosure.current.open = false;
        if (restoreFocus) trigger.current.focus();
    }

    function navigate(event) {
        if (event.key === "Escape" && disclosure.current.open) {
            event.preventDefault();
            close(true);
            return;
        }
        if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        disclosure.current.open = true;
        const buttons = [...disclosure.current.querySelectorAll(".rec-filter-option")];
        const current = buttons.indexOf(event.target);
        const active = options.findIndex((option) => option.id === value);
        let target = active < 0 ? 0 : active;
        if (event.key === "Home") target = 0;
        if (event.key === "End") target = buttons.length - 1;
        if (current !== -1 && event.key === "ArrowDown") target = (current + 1) % buttons.length;
        if (current !== -1 && event.key === "ArrowUp") target = (current + buttons.length - 1) % buttons.length;
        buttons[target]?.focus();
    }

    return (
        <details ref={disclosure} className="rec-filter" name="recommendation-filter"
            onKeyDown={navigate}
            onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) close(false);
            }}>
            <summary ref={trigger}>
                <FilterIcon option={selected} />
                <span><small>{label}</small><strong>{selected.label}</strong></span>
                <svg className="rec-filter-chevron" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                    <path d="m3 5 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
            </summary>
            <div className="rec-filter-options" role="group" aria-label={label + " options"}>
                {options.map((option) => (
                    <button type="button" className="rec-filter-option" key={option.id}
                        aria-pressed={option.id === value} onClick={() => {
                            onChange(option.id);
                            close(true);
                        }}>
                        <FilterIcon option={option} />
                        <span>{option.label}{option.detail && <small>{option.detail}</small>}</span>
                        {option.id === value && <span className="rec-filter-check" aria-hidden="true">✓</span>}
                    </button>
                ))}
            </div>
        </details>
    );
}

export default function RecommendationFilters({ position, rank, playerRank, onPosition, onRank }) {
    const tier = Math.floor(playerRank / 10);
    const positionOptions = positions.map(([id, label, path]) => ({ id, label, path }));
    const rankOptions = [
        { id: "", label: "Player rank", detail: ranks[tier], medal: tier >= 1 && tier <= 8 ? tier : null },
        ...[3, 4, 5, 6].map((medal) => ({ id: String(medal), label: ranks[medal], medal })),
    ];

    return (
        <div className="rec-filter-bar">
            <RecommendationFilter label="Position" value={position} options={positionOptions} onChange={onPosition} />
            <RecommendationFilter label="Rank" value={rank} options={rankOptions} onChange={onRank} />
        </div>
    );
}

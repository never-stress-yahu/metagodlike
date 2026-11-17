import { useState } from "react";
import useApi from "../useApi";

const itemOrder = new Map([
    [44, 0], // Tango
    [20, 1], // Circlet
    [29, 2], // Boots of Speed
    [16, 3], // Iron Branch
    [42, 5], // Observer Ward
    [43, 6], // Sentry Ward
    [218, 7], // Combined wards
]);
const stackableItems = new Set([44, 42, 43, 218]);
const stages = [
    ["start", "Start", "Opening buy"],
    ["mid", "Mid", "35 min"],
    ["late", "Late", "50+ min"],
];
const difficultyStyle = { Simple: "simple", Moderate: "moderate", Complex: "complex" };

function slotName(item) {
    return item.name + (item.quantity > 1 ? " ×" + item.quantity : "");
}

function SlotArtwork({ item }) {
    return (
        <>
            {item.image_url ? <img src={item.image_url} alt="" loading="lazy" /> : <span>{item.name}</span>}
            {item.quantity > 1 && (
                <span className="inventory-quantity" aria-hidden="true">×{item.quantity}</span>
            )}
        </>
    );
}

function StartingInventory({ items, gold, ranked = false }) {
    const [selectedSlot, setSelectedSlot] = useState(null);
    const ordered = ranked ? items : [...items].sort((a, b) => (itemOrder.get(a.item_id) ?? 4) - (itemOrder.get(b.item_id) ?? 4));
    const slots = ordered.flatMap((item) => stackableItems.has(item.item_id)
        ? [item]
        : Array.from({ length: item.quantity ?? 1 }, () => ({ ...item, quantity: 1 })));
    const selected = slots[selectedSlot];
    const extra = slots.slice(9);

    return (
        <div className="starting-inventory">
            {gold != null && <div className="inventory-gold">{gold} gold</div>}
            <ul className="inventory-slots" aria-label="Starting inventory">
                {Array.from({ length: 6 }, (_, index) => {
                    const item = slots[index];
                    return (
                        <li className="inventory-slot" key={index} aria-hidden={item ? undefined : true}>
                            {item && (
                                <button type="button" aria-label={slotName(item)} title={slotName(item)}
                                    aria-pressed={index === selectedSlot}
                                    onClick={() => setSelectedSlot(index === selectedSlot ? null : index)}>
                                    <SlotArtwork item={item} />
                                </button>
                            )}
                            <span className="inventory-slot-number" aria-hidden="true">{index + 1}</span>
                        </li>
                    );
                })}
            </ul>
            {!ranked && <ul className="inventory-slots inventory-backpack" aria-label="Backpack">
                {Array.from({ length: 3 }, (_, index) => {
                    const item = slots[index + 6];
                    return (
                        <li className="inventory-slot" key={index} aria-hidden={item ? undefined : true}>
                            {item && (
                                <div className="backpack-item" role="img"
                                    aria-label={slotName(item) + " · " + item.cost + " gold each"}
                                    title={slotName(item) + " · " + item.cost + " gold each"}>
                                    <SlotArtwork item={item} />
                                </div>
                            )}
                        </li>
                    );
                })}
            </ul>}
            {selected && (
                <p className="inventory-item-info" role="status">
                    <strong>{selected.name}</strong> · {selected.cost} gold each
                    {selected.purchases ? " · " + selected.purchases + " purchases" : ""}
                </p>
            )}
            {extra.length > 0 && (
                <p className="inventory-item-info">Additional purchases · {extra.map(slotName).join(", ")}</p>
            )}
        </div>
    );
}

export default function StartingItems({ hero, position, showIcon = true, difficulty }) {
    const [open, setOpen] = useState(false);
    const [stage, setStage] = useState("start");
    const base = "/heroes/" + hero.hero_id;
    const starting = useApi(open && position ? base + "/starting-items?position=" + position : null);
    const later = useApi(open && position ? base + "/game-items?position=" + position : null);
    const request = stage === "start" ? starting : later;
    const data = stage === "start" ? request.data : null;
    const stageItems = stage === "start" ? undefined : request.data?.[stage];

    return (
        <details className="starting-items" onToggle={(event) => setOpen(event.currentTarget.open)}>
            <summary className="items-trigger">
                {showIcon && (hero.image_url || hero.icon_url) && (
                    <img className="items-hero-image" src={hero.image_url || hero.icon_url} alt="" loading="lazy" />
                )}
                <span className="items-hero-identity">
                    <strong>{hero.name}</strong>
                    {difficulty && <span className={"hero-difficulty difficulty-" + (difficultyStyle[difficulty] || "unknown")}>{difficulty}</span>}
                </span>
                <span className="items-action">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
                        <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3zm0 9 8-4.5M4 7.5l8 4.5v9" />
                    </svg>
                    Items <span className="items-chevron" aria-hidden="true">⌄</span>
                </span>
            </summary>
            <div className="items-panel">
                <div className="inventory-stage-selector" role="group" aria-label="Game stage">
                    {stages.map(([id, label, timing]) => (
                        <button type="button" key={id} aria-label={label} aria-pressed={stage === id} onClick={() => setStage(id)}>
                            <strong>{label}</strong><small>{timing}</small>
                        </button>
                    ))}
                </div>
                {request.loading && <p role="status">Loading items…</p>}
                {stage !== "start" && request.data && (
                    <>
                        {stageItems ? (
                            <>
                                <p className="data-warnings">
                                    OpenDota · {stage === "mid" ? "Estimated inventory at 35 min" : "Six-slot final inventory · " + stageItems.minute + " min"}
                                    {" · "}{stageItems.position_match ? "Selected position (estimated)" : "Example from another or unknown position"}
                                    {stageItems.start_time && " · " + new Date(stageItems.start_time * 1000).toLocaleDateString()}
                                </p>
                                <StartingInventory key={stage} items={stageItems.items} gold={stageItems.gold} ranked />
                            </>
                        ) : <p>{stage === "late"
                            ? "No six-slot inventory from a 50+ minute match in the available sample."
                            : "No mid-game inventory at minute 35 in the available sample."}</p>}
                    </>
                )}
                {request.error && (
                    <p role="alert">
                        {request.error.message} <button type="button" className="starting-items-retry" onClick={request.retry}>Retry</button>
                    </p>
                )}
                {data?.bundles.length > 0 && (
                    <>
                        <p className="data-warnings">
                            OpenDota · {data.sample_size} recent parsed matches
                            {" · "}{data.mode === "selected_position" ? "Selected position (estimated)" : "All positions"}.
                        </p>
                        {data.bundles.map((bundle, index) => (
                            <div className="starting-bundle" key={index}>
                                <p>Seen in {bundle.observed_count}/{data.sample_size} matches</p>
                                <StartingInventory items={bundle.items} gold={bundle.gold} />
                            </div>
                        ))}
                    </>
                )}
                {data?.mode === "item_popularity" && (
                    <>
                        <p className="data-warnings">OpenDota · Individual starting item popularity across positions.</p>
                        {data.popular_items.length ? <StartingInventory items={data.popular_items} /> : <p>No starting items were reported.</p>}
                    </>
                )}
                {later.data?.benchmarks && (
                    <div className="inventory-networth">
                        <p><strong>Typical farm</strong> · Sample medians</p>
                        <ul>
                            {later.data.benchmarks.map((point) => {
                                const hits = later.data.last_hits_benchmarks?.find((row) => row.minute === point.minute);
                                return (
                                    <li key={point.minute}>
                                        <strong>{point.minute} min</strong>
                                        <span>{point.gold == null ? "—" : point.gold.toLocaleString() + " gold"}</span>
                                        <small>{point.gold == null ? "Fewer than 3 matches"
                                            : point.sample_size + (point.position_match ? " matches in role" : " matches across roles")}</small>
                                        <span>{hits?.last_hits == null ? "— last hits" : hits.last_hits.toLocaleString() + " last hits"}</span>
                                        <small>{hits?.last_hits == null ? "Fewer than 3 matches"
                                            : hits.sample_size + (hits.position_match ? " matches in role" : " matches across roles")}</small>
                                    </li>
                                );
                            })}
                        </ul>
                    </div>
                )}
            </div>
        </details>
    );
}

import { useEffect, useState } from "react";
import katex from "katex";
import { logicFormulas } from "./logicFormulas";
import { logicStagesEn } from "./logicStages.en.js";
import { logicStagesRu } from "./logicStages.ru.js";
import "katex/dist/katex.min.css";
import "./Logic.css";

const languageKey = "dota-analytics.logic-language";
const translations = {
    en: {
        title: "Logic",
        description: "How metagodlike turns match data into stats, recommendations, and benchmarks.",
        language: "Logic page language",
        contents: "Contents",
        contentsLabel: "Logic page contents",
        input: "Input",
        calculation: "Calculation",
        output: "Output",
        formulas: "Formulas",
        stages: logicStagesEn,
    },
    ru: {
        title: "Логика",
        description: "Как metagodlike превращает данные о матчах в статистику, рекомендации и ориентиры по игре.",
        language: "Язык вкладки Logic",
        contents: "Содержание",
        contentsLabel: "Разделы алгоритмов",
        input: "Вход",
        calculation: "Расчёт",
        output: "Выход",
        formulas: "Формулы",
        stages: logicStagesRu,
    },
};

const renderedFormulas = Object.fromEntries(
    Object.entries(logicFormulas).map(([id, steps]) => [
        id,
        steps.map((formulas) => formulas?.map((tex) => ({
            tex,
            html: katex.renderToString(tex, { displayMode: true }),
        }))),
    ]),
);

function initialLanguage() {
    try {
        return localStorage.getItem(languageKey) === "ru" ? "ru" : "en";
    } catch {
        return "en";
    }
}

function Logic() {
    const [language, setLanguage] = useState(initialLanguage);
    const copy = translations[language];

    useEffect(() => {
        const stageId = window.location.hash.slice(1);
        if (logicStagesEn.some(({ id }) => id === stageId)) {
            document.getElementById(stageId)?.scrollIntoView();
        }
    }, []);

    function changeLanguage(nextLanguage) {
        setLanguage(nextLanguage);
        try {
            localStorage.setItem(languageKey, nextLanguage);
        } catch {
            // The switch still works for this visit if storage is unavailable.
        }
    }

    return (
        <div className="logic-page" lang={language}>
            <header className="dashboard-title logic-heading">
                <div>
                    <h1>{copy.title}</h1>
                    <p>{copy.description}</p>
                </div>
                <div className="logic-language" role="group" aria-label={copy.language}>
                    <button type="button" lang="en" aria-label="English" aria-pressed={language === "en"}
                        onClick={() => changeLanguage("en")}>EN</button>
                    <button type="button" lang="ru" aria-label="Русский" aria-pressed={language === "ru"}
                        onClick={() => changeLanguage("ru")}>RU</button>
                </div>
            </header>

            <div className="logic-layout">
                <nav className="logic-index" aria-label={copy.contentsLabel}>
                    <h2>{copy.contents}</h2>
                    <ol>
                        {copy.stages.map(({ id, nav }) => (
                            <li key={id}>
                                <a href={`#${id}`}>{nav}</a>
                            </li>
                        ))}
                    </ol>
                </nav>

                <div className="logic-stages">
                    {copy.stages.map(({ id, title, input, steps, output }, index) => (
                        <section className="logic-stage" key={id} id={id} tabIndex={-1} aria-labelledby={`${id}-title`}>
                            <header className="logic-stage-heading">
                                <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                                <h2 id={`${id}-title`}>{title}</h2>
                            </header>
                            <div className="logic-stage-boundary">
                                <h3>{copy.input}</h3>
                                <p>{input}</p>
                            </div>
                            <div className="logic-calculation">
                                <h3>{copy.calculation}</h3>
                                {steps.map(({ title: stepTitle, body }, stepIndex) => {
                                    const formulas = renderedFormulas[id]?.[stepIndex];
                                    return (
                                        <div className="logic-step" key={stepIndex}>
                                            <h4>{stepTitle}</h4>
                                            <p>{body}</p>
                                            {formulas && (
                                                <ul className="logic-formulas" aria-label={copy.formulas}>
                                                    {formulas.map(({ tex, html }) => (
                                                        <li key={tex} dangerouslySetInnerHTML={{ __html: html }} />
                                                    ))}
                                                </ul>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                            <div className="logic-stage-boundary logic-stage-output">
                                <h3>{copy.output}</h3>
                                <p>{output}</p>
                            </div>
                        </section>
                    ))}
                </div>
            </div>
        </div>
    );
}

export default Logic;

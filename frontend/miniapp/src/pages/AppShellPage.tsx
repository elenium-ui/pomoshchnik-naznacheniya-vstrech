import styles from "./AppShellPage.module.scss";

export function AppShellPage() {
  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <div className={styles.brand}>ER Meet</div>
        <h1>Mini App Stage 1</h1>
        <p>Технический экран каркаса Mini App. Бизнес-функционал будет добавляться по этапам.</p>
        <ul>
          <li>Frontend runtime: ready</li>
          <li>API health route: /health</li>
          <li>API smoke route: /api/miniapp/smoke</li>
        </ul>
      </section>
    </main>
  );
}


function ResultCard({ title, loading, children }) {
  return (
    <section className="result-card">
      <h3>{title}</h3>
      {loading ? <p className="loading-text">Loading...</p> : children}
    </section>
  );
}

window.ResultCard = ResultCard;

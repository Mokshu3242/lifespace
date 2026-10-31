/** For judges and curious users: what happens, which model does what, and what code checks. */
export default function HowItWorks({ models }) {
  return (
    <article className="how">
      <h1>How LifeSpace works</h1>
      <p className="lead">
        One idea runs through everything: <strong>the AI suggests, code checks.</strong> Meta&apos;s models do the
        reading, planning and talking. Every number on screen is measured on your plan.
      </p>

      <section>
        <h2>1. Reading the plan</h2>
        <ul>
          <li>Code (OpenCV) finds walls, doors, the outside, and closed furniture shapes. Thin door lines become open
            doorways, so people can walk through.</li>
          <li>Printed names and sizes are read with OCR. A printed name always wins.</li>
          <li>Rooms with no printed name are named by <strong>Muse Spark</strong> from a zoomed tile, with a reason.</li>
          <li>Scale comes from printed room sizes, or from chairs (about 22 in each) when there are none.</li>
          <li>The front door is found from the printed “Entrance” label.</li>
        </ul>
      </section>

      <section>
        <h2>2. The people</h2>
        <ul>
          <li>You describe them in words. <strong>Muse Spark</strong> fills in name, age, how they get around, their
            bedroom and a usual day.</li>
          <li>Body width comes from standard sizes, never from the model: walker 25 in, wheelchair 30 in, cane 26 in,
            child 16 in.</li>
        </ul>
      </section>

      <section>
        <h2>3. The redesign</h2>
        <ul>
          <li><strong>Muse Spark</strong> picks changes from a catalog of real, common items with standard sizes and
            typical prices, and says why for each.</li>
          <li>Code keeps only what passes: the item exists, belongs in that room, fits the budget, isn&apos;t a
            duplicate, and isn&apos;t a built-in (toilets, tubs, stoves stay).</li>
          <li>Each item is carried in from the front door at its real size. If a sofa can&apos;t get through a door,
            a smaller real item is tried.</li>
          <li>Obvious spots are tried first and rejected with a reason (blocks the doorway, no wall behind it). Every
            room must stay reachable from the entrance.</li>
          <li><strong>Keep improving</strong> runs up to three rounds: design, live the day, score, tell the model what
            is still wrong. It stops when the target is met or only door work is left.</li>
        </ul>
      </section>

      <section>
        <h2>4. Living the day</h2>
        <ul>
          <li>Each person walks their routine on the 6 in grid (A* paths), only where a square their width fits.</li>
          <li>The same day runs before and after, so the comparison is fair.</li>
          <li>The scorecard is computed by code: safety, access (walker or wheelchair reach, 5 ft turning circle),
            movement, energy. Things furniture can&apos;t fix, like a narrow door, are flagged.</li>
          <li><strong>Muse Spark</strong> writes one line in each person&apos;s voice, from the measured facts only.</li>
          <li><strong>Muse Image</strong> draws a redesigned room from its real items.</li>
        </ul>
      </section>

      <section>
        <h2>Meta models used</h2>
        <ul className="models">
          {models.map((m) => <li key={m.name}><strong>Meta {m.name}</strong> {m.does}</li>)}
        </ul>
      </section>

      <section>
        <h2>Limits, honestly</h2>
        <ul>
          <li>Door widths are measured on a 6 in grid, so about ±3 in.</li>
          <li>Furniture drawn as open lines isn&apos;t detected; add it in the editor.</li>
          <li>Prices are typical US retail, not live store prices.</li>
          <li>Scores are for comparing designs, not medical, safety or accessibility advice.</li>
        </ul>
      </section>

      <a href="#/" className="file-btn">Try it with your floor plan</a>
    </article>
  )
}

import {
  FleetCards, FleetMessages, ProposalInbox, RunDrawer, RunHistory, RuntimeNotice, useFleet,
} from '../components/fleet'
import { ManagerPanel } from '../components/ManagerPanel'

/** The full console: a task box per agent, every proposal, and the run history
    with transcripts. The home page carries a compact version of the first two. */
export function Agents({ onChanged }: { onChanged?: () => void }) {
  const f = useFleet(onChanged)
  const rt = f.fleet?.runtime

  return (
    <>
      <ManagerPanel onChanged={() => { void f.refresh(); onChanged?.() }} />

      <section className="sec">
        <div className="sec-head">
          <h2>Agent fleet</h2>
          <span className="spacer" />
          {rt && <span className="sub">running locally on {rt.model}</span>}
        </div>
        <p className="sec-note">
          Three agents, one domain each. Every agent can read its own corner of the school and
          <b> propose </b>changes — it can never make one. A proposal is validated, shown with the
          evidence behind it, and applied by deterministic code only after a person approves it.
          That boundary is what makes a small local model safe to point at a school's records.
        </p>
        <RuntimeNotice f={f} />
        <FleetMessages f={f} />
        <FleetCards f={f} />
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2>Waiting for approval</h2>
          <span className="spacer" />
          <span className="sub">{f.proposals.length} pending</span>
        </div>
        <p className="sec-note">
          Nothing here has happened yet. Approving runs deterministic code that re-checks the
          proposal against current records — a seat that filled or a plan opened since will be
          refused rather than forced through.
        </p>
        <ProposalInbox f={f} />
      </section>

      <section className="sec">
        <div className="sec-head">
          <h2>Run history</h2>
          <span className="spacer" />
          <button className="btn sm ghost" onClick={() => void f.refresh()}>Refresh</button>
        </div>
        <RunHistory f={f} />
      </section>

      <RunDrawer f={f} />
    </>
  )
}

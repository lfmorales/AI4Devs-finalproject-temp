import { AdformName } from "@/features/linking/AdformName";
import { Modal } from "@/lib/components/Modal";

interface UnlinkDialogProps {
  campaignName: string;
  lineItemName: string;
  submitting: boolean;
  /** A Spanish message about the last attempt, shown inside the dialog. */
  problem: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Says what unlinking destroys, and sends nothing until it is confirmed. */
export function UnlinkDialog({ campaignName, lineItemName, submitting, problem, onConfirm, onCancel }: UnlinkDialogProps) {
  return (
    <Modal title="Desvincular la pareja" closable={!submitting} onClose={onCancel}>
      <p>
        Se borrarán los días de entrega ingeridos de la línea vinculada a <AdformName name={campaignName} /> / <AdformName name={lineItemName} />. Esta acción no se puede deshacer.
      </p>
      {problem && <div role="alert" style={{ backgroundColor: "#fee2e2", padding: "0.75rem", margin: "0.5rem 0" }}>{problem}</div>}
      <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
        <button type="button" className="btn-danger" disabled={submitting} onClick={onConfirm}>Confirmar desvinculación</button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}

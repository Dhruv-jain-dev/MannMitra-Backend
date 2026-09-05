import { ShieldCheck } from "lucide-react";

export default function PrivacyNote({ children }) {
  return <div className="privacy-footer"><ShieldCheck size={18} /><div><b>DPDP Act-aligned privacy design</b><p>{children}</p></div></div>;
}

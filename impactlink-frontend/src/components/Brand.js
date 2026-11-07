import "./Brand.css";

export default function Brand({ href = "/", className = "" }) {
  return <a href={href} className={`impactlink-brand ${className}`} aria-label="ImpactLink home">
    <img src={`${process.env.PUBLIC_URL || ""}/impactlink-mark.svg`} width="36" height="36" alt="" />
    <span>Impact<span className="impactlink-brand-link">Link</span></span>
  </a>;
}

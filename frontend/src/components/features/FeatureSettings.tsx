import { ShieldCheck, SlidersHorizontal } from "lucide-react";

import type { FeatureRead } from "../../types/api";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

export function FeatureSettings({ feature }: { feature: FeatureRead | null }) {
  return (
    <div className="tab-content two-column">
      <section className="surface">
        <div className="section-title">
          <SlidersHorizontal aria-hidden="true" size={18} />
          <h2>特性设置</h2>
        </div>
        <label className="field-label">
          名称
          <Input
            readOnly
            value={feature?.name ?? ""}
            placeholder="选择一个特性后显示"
          />
        </label>
        <label className="field-label">
          描述
          <Textarea
            readOnly
            value={feature?.description ?? ""}
            placeholder="维护特性的业务边界和常见问题"
          />
        </label>
      </section>
      <section className="surface">
        <div className="section-title">
          <ShieldCheck aria-hidden="true" size={18} />
          <h2>治理信息</h2>
        </div>
        <dl className="meta-grid">
          <dt>Owner</dt>
          <dd>{feature?.owner_subject_id ?? "未创建"}</dd>
          <dt>更新时间</dt>
          <dd>
            {feature ? new Date(feature.updated_at).toLocaleString() : "-"}
          </dd>
        </dl>
      </section>
    </div>
  );
}

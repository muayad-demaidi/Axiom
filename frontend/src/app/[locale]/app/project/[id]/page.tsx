import { ProjectWorkspace } from "@/components/product/ProjectWorkspace";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const projectId = Number(id);
  return <ProjectWorkspace projectId={projectId} />;
}

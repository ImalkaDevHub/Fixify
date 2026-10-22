import { z } from "zod";

export const projectFormSchema = z.object({
  name: z.string().trim().min(1, "Enter a project name.").max(100, "Use 100 characters or fewer."),
  website_url: z
    .string()
    .trim()
    .max(2048, "Use a URL with 2,048 characters or fewer.")
    .url("Enter a valid website URL.")
    .refine((value) => /^https?:\/\//i.test(value), "Website URL must use HTTP or HTTPS."),
  repo_full_name: z
    .string()
    .trim()
    .optional()
    .transform((value) => (value ? value : undefined))
    .refine((value) => !value || value.length <= 100, "Use 100 characters or fewer.")
    .refine((value) => !value || /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value), {
      message: "Use the owner/repository format.",
    }),
  default_branch: z.string().trim().max(255, "Use 255 characters or fewer.").optional(),
});

export type ProjectFormValues = z.input<typeof projectFormSchema>;
export type ProjectCreateInput = z.output<typeof projectFormSchema>;

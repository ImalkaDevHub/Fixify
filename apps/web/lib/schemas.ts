import { z } from "zod";

/** Mirrors the backend rules so most problems are caught before a request. */
export const passwordSchema = z
  .string()
  .min(10, "Use at least 10 characters.")
  .max(128, "Use at most 128 characters.")
  .refine((value) => value.trim().length > 0, "The password cannot be only spaces.");

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

export const registerSchema = z.object({
  display_name: z.string().trim().min(1, "Enter your name.").max(100, "Use 100 characters or fewer."),
  email: z.string().trim().email("Enter a valid email address.").max(320),
  password: passwordSchema,
});

export const resetSchema = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((data) => data.password === data.confirm, { message: "The passwords do not match.", path: ["confirm"] });

const repository = z
  .string()
  .trim()
  .optional()
  .refine(
    (value) => !value || (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value) && !value.split("/").some((p) => p === "." || p === "..")),
    "Use the owner/repository format.",
  );

export const projectSchema = z.object({
  name: z.string().trim().min(1, "Enter a project name.").max(100, "Use 100 characters or fewer."),
  website_url: z
    .string()
    .trim()
    .max(2048, "Use a URL with 2,048 characters or fewer.")
    .url("Enter a valid website URL.")
    .refine((value) => /^https?:\/\//i.test(value), "The URL must start with http:// or https://."),
  description: z.string().trim().max(500, "Use 500 characters or fewer.").optional(),
  repo_full_name: repository,
  scan_max_links: z
    .string()
    .optional()
    .refine((value) => !value || (/^\d+$/.test(value) && Number(value) <= 200), "Enter a number from 0 to 200."),
});

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type ResetValues = z.infer<typeof resetSchema>;
export type ProjectFormValues = z.input<typeof projectSchema>;

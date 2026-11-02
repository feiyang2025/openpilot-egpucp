#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_2888912773465460112);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_5859204138557633979);
void pose_H_mod_fun(double *state, double *out_5221902563181446422);
void pose_f_fun(double *state, double dt, double *out_1175449659287803657);
void pose_F_fun(double *state, double dt, double *out_1771814395118668150);
void pose_h_4(double *state, double *unused, double *out_6579517944273218715);
void pose_H_4(double *state, double *unused, double *out_626179243570512299);
void pose_h_10(double *state, double *unused, double *out_1705430589688773801);
void pose_H_10(double *state, double *unused, double *out_7777681021109994334);
void pose_h_13(double *state, double *unused, double *out_5206051105996912215);
void pose_H_13(double *state, double *unused, double *out_2586094581761820502);
void pose_h_14(double *state, double *unused, double *out_9171638683540642626);
void pose_H_14(double *state, double *unused, double *out_1061295770215395898);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}
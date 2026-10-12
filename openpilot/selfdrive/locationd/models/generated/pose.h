#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_5466562818920560471);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_1362104546618899903);
void pose_H_mod_fun(double *state, double *out_1079315633669929618);
void pose_f_fun(double *state, double dt, double *out_5100720361949642007);
void pose_F_fun(double *state, double dt, double *out_3380236388623495731);
void pose_h_4(double *state, double *unused, double *out_6455932907869978741);
void pose_H_4(double *state, double *unused, double *out_1833476635724642225);
void pose_h_10(double *state, double *unused, double *out_7550405242873940214);
void pose_H_10(double *state, double *unused, double *out_4785130908546047591);
void pose_h_13(double *state, double *unused, double *out_9187434641215416987);
void pose_H_13(double *state, double *unused, double *out_9002636229668208462);
void pose_h_14(double *state, double *unused, double *out_8472317454123513856);
void pose_H_14(double *state, double *unused, double *out_5796717492064126754);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}